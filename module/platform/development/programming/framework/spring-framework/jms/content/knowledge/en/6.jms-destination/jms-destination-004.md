# JndiDestinationResolver and Administered Object Lookup

## Learning objectives

When integrating JMS with an application server, enterprises often do not want Java code to decide physical Queues or Topics for each environment. Administrators can publish JMS resources under stable **JNDI names**, while the application only knows those logical names. In Spring JMS, `JndiDestinationResolver` is the bridge between a logical name and a `jakarta.jms.Destination` object.

After this lesson, you will be able to:

- Explain **JMS administered objects**, the difference between a **JNDI** name, an actual Queue/Topic name on the broker, and a connection address.
- Understand when `JndiDestinationResolver` looks up a `Queue`/`Topic`, when it uses caching, and how fallback to dynamic destinations works.
- Configure `JndiDestinationResolver` with `JmsTemplate` and `@JmsListener`; understand why both sides must be configured properly.
- Use application-server JNDI (`java:comp/env/...`) or Apache ActiveMQ Artemis client-side JNDI for practice.
- Diagnose missing bindings, Queue/Topic mismatches, stale caches, wrong providers, and broker connection errors without confusing their root causes.

This lesson uses **Spring Framework 6.x / Spring Boot 3.5.x, Java 17+, and Jakarta Messaging 3.x**. In older Spring/JMS versions, APIs may reside in `javax.jms`; Java JNDI still uses package `javax.naming`, **even after JMS moved to `jakarta.jms`**.

## 1. What are JNDI and JMS administered objects?

### 1.1. JNDI is not a broker Queue

**JNDI** (*Java Naming and Directory Interface*) is a mechanism for looking up Java resources from a naming context (`Context`). The application calls `lookup("jms/Orders")` and receives an object registered under that name. In JMS, objects commonly administered and exposed via JNDI include:

| Administered object type | Java type | Purpose |
| --- | --- | --- |
| Connection factory | `jakarta.jms.ConnectionFactory` | Holds configuration for creating JMS connections to the provider/broker. |
| Queue | `jakarta.jms.Queue` | Represents a point-to-point destination. |
| Topic | `jakarta.jms.Topic` | Represents a publish/subscribe destination. |

**Do not conflate the three naming layers:**

```text
Name sent by application:   "jms/Orders"
              |
              | JndiDestinationResolver
              v
JNDI lookup("jms/Orders") -> jakarta.jms.Queue
              |
              | JMS provider knows queueName
              v
Queue on broker:            "orders.queue"
```

- `jms/Orders` is the **binding name in JNDI** that the application looks up. It does not have to match the physical Queue.
- `orders.queue` is the **broker-side Queue name** that the JMS object points to in the illustrative configuration.
- `tcp://localhost:61616` is the **broker connection address**, not a Destination name.
- `ConnectionFactory` knows how to connect; `Destination` represents where to send/receive. Spring needs both.

For example, if another environment uses physical Queue `orders.production`, an administrator can rebind `jms/Orders` to the new Queue while the service code continues calling the same name. Changing the effective mapping may require clearing the cache or restarting the application, depending on the provider and resolver settings.

### 1.2. "Administered" means managed by whom?

In a Jakarta EE environment or an application with a resource adapter, the application server can create/publish ConnectionFactory, Queue, and Topic in the naming context. Business code does not need to construct each object itself via `session.createQueue(...)`.

However, **JNDI does not necessarily mean a standalone JNDI server**. Apache ActiveMQ Artemis provides a **client-side JNDI implementation**: based on `queue.*` / `topic.*` properties, the client itself instantiates Java `Queue` / `Topic` objects for lookup. **The Artemis broker does not run a JNDI server, and client-side bindings do not create a physical Queue on the broker.** The broker must already have the matching address/queue or support auto-create per policy.

Therefore, distinguish:

1. **Administered object in JNDI:** configuration/representation layer on the client or application server.
2. **Actual broker resource:** Queue, Topic/address, routing, access permissions, persistence, dead-letter policy, and limits.
3. **JMS connection/session:** runtime resources created for sending/receiving once the factory and destination are known.

A successful JNDI lookup proves the binding exists and returns a matching object; it **does not prove the broker is online, the user has permissions, the physical Queue exists, or messages have been processed**.

## 2. How does Spring turn a destination name into an object?

In Spring JMS, `org.springframework.jms.support.destination.DestinationResolver` has the core method:

```java
Destination resolveDestinationName(
        Session session,
        String destinationName,
        boolean pubSubDomain) throws JMSException;
```

This is an API signature explaining the mechanism, not a standalone Java program. `destinationName` is the string from `JmsTemplate` or the listener container; `pubSubDomain=false` means a Queue is expected, and `true` means a Topic is expected.

### 2.1. DynamicDestinationResolver — common default

`DynamicDestinationResolver` is the default resolver of `JmsTemplate` when nothing else is configured. It uses the JMS `Session` to create an object representing the destination using the passed-in name: `session.createQueue(name)` or `session.createTopic(name)`. It does not require looking up JNDI.

Example:

```java
jmsTemplate.convertAndSend("orders.queue", "order-123");
```

If the template uses the default resolver and `pubSubDomain=false`, the string `orders.queue` is interpreted as a Queue name. **Calling `createQueue` does not guarantee that the broker creates a physical Queue**; the outcome depends on the broker/provider.

### 2.2. JndiDestinationResolver — looking up published objects

`org.springframework.jms.support.destination.JndiDestinationResolver` is used when the application's string is a **JNDI name**, not a physical Queue/Topic name.

```java
JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setCache(true);
resolver.setFallbackToDynamicDestination(false);

jmsTemplate.setDestinationResolver(resolver);
jmsTemplate.convertAndSend("jms/Orders", "order-123");
```

This is **illustrative code inside a Spring configuration that already has `jmsTemplate` and a JNDI context**; it does not run standalone. When sending, Spring asks the resolver to look up `jms/Orders`, receives a `Queue`, and uses that Queue as the producer's target.

Conceptual flow:

```text
JmsTemplate.convertAndSend("jms/Orders", payload)
    |
    v
JndiDestinationResolver.resolveDestinationName(
        session, "jms/Orders", false)
    |
    +-- cache has binding? --> use cached object
    |
    +-- not in cache --> JNDI lookup "jms/Orders"
                         |
                         +-- Queue found --> verify matching type --> cache --> return Queue
                         |
                         +-- not found --> fallback enabled?
                                                   |
                                                   +-- no: throw error
                                                   +-- yes: DynamicDestinationResolver
```

During lookup, the resolver checks the destination type against the Queue/Topic requested by the caller. A JNDI name returning a `Topic` when the template is using Queue mode can cause a **domain mismatch** error, which should not be fixed by arbitrarily renaming strings.

## 3. Key settings of JndiDestinationResolver

| Setting | Default in Spring Framework 6.x | Meaning |
| --- | --- | --- |
| `setCache(true/false)` | `true` | Caches looked-up `Destination` by name to avoid hitting JNDI every time. |
| `setFallbackToDynamicDestination(true/false)` | `false` | If JNDI lookup fails, should it use the dynamic resolver to create a destination object? |
| `setResourceRef(true/false)` | `false` | For application server resource references, prepends `java:comp/env/` to relative names when needed. |
| `setJndiEnvironment(Properties)` | No custom environment specified | Supplies `InitialContext` parameters for a specific JNDI provider. |
| `setJndiTemplate(JndiTemplate)` | Uses standard JNDI behavior | Customizes lookup logic or uses an already configured JNDI template. |
| `setDynamicDestinationResolver(...)` | Standard `DynamicDestinationResolver` | Replaces the fallback strategy when fallback is enabled. |

### 3.1. The cache caches Destination objects, not messages

When `cache=true`, the first lookup of `jms/Orders` fetches the `Destination` from JNDI, and subsequent calls typically reuse the stored object. This cache **does not hold messages, does not mean connections/sessions are cached, and does not guarantee that the broker Queue is preserved**.

If an admin rebinds `jms/Orders` to a new Queue object while the application is running, the cache may retain the old object. You can use:

```java
resolver.removeFromCache("jms/Orders"); // Remove a single binding.
resolver.clearCache();                  // Remove all bindings.
```

These two calls are **operational snippets** on an existing resolver bean. Clear the cache only with good reason; for major broker/routing changes, test reconnecting and stopping receivers properly rather than assuming clearing the cache is sufficient.

You can disable caching with `setCache(false)` if re-lookup on every operation is needed, but this increases JNDI overhead and depends on naming-provider availability. For some listeners, lookup happens when the container starts or creates the consumer; changing cache settings does not guarantee a running listener switches to the new destination immediately.

**Pitfall:** `JndiDestinationResolver`'s cache keys by **name**, without separating Queue and Topic independently. Avoid sharing the same JNDI name for both a Queue and a Topic when caching is enabled.

### 3.2. Fallback defaults to false — keep it strict when admin governance is required

`setFallbackToDynamicDestination(false)` ensures wrong JNDI names are caught rather than silently creating objects from those strings.

Suppose code accidentally calls `jms/Ordres` instead of `jms/Orders`:

- **Fallback=false:** lookup fails; the application sees the configuration/binding error.
- **Fallback=true:** the resolver may call `session.createQueue("jms/Ordres")`. Depending on the broker, it may point to a wrong Queue or be auto-created, making the bug hard to spot.
- Having fallback enabled **does not mean** the provider guarantees the physical Queue will be auto-created or messages will reach the right business consumer.

When a system requires admin-prepared resources and has clear naming policies, **fail-fast-by-design** configuration helps detect typos, permission issues, and wrong mappings early.

### 3.3. Resource names like java:comp/env

In an application server, published names may look like:

```text
java:comp/env/jms/Orders
java:comp/env/jms/BillingTopic
```

With `resolver.setResourceRef(true)`, calling the relative name `jms/Orders` can be normalized by Spring to `java:comp/env/jms/Orders`. If the string already has a scheme, such as `java:comp/env/jms/Orders`, Spring does not prepend the prefix again. **The default value of `resourceRef` is `false`**, suitable when the JNDI provider does not use this namespace.

Do not blindly switch every deployment to `resourceRef=true`: Artemis client-side JNDI in the example below uses the alias `jms/Orders`, not the `java:comp/env/` naming context.

## 4. Complete example: looking up a Queue via JNDI in Spring Boot

This example uses **Java 17+, Spring Boot 3.5.8, and Artemis Jakarta JMS client**. The goal is to verify that publisher and consumer code both use the JNDI name `jms/Orders` while the actual Queue is configured as `orders.queue`.

### 4.1. Prerequisites to run

- Java 17+ and Maven available.
- An Apache ActiveMQ Artemis broker ready at `tcp://localhost:61616` or an equivalent endpoint.
- A JMS account allowed to send/receive. Supply `JMS_USERNAME` and `JMS_PASSWORD` via environment variables; do not hardcode secrets in source.
- The broker has Queue `orders.queue`, or matching auto-create is enabled. **`jndi.properties` only configures client-side Queue objects**, not broker configuration.
- Avoid running multiple other apps concurrently competing on the same Queue if you want clean log correlation during practice.

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>jndi-destination-demo</artifactId>
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
```

`spring-boot-starter-artemis` brings in `spring-jms` and the Artemis Jakarta client under Spring Boot's dependency management. Because this example instantiates the native connection factory in code, you do not need to set `spring.artemis.*` simultaneously; the example's own settings use the `app.jms.*` namespace to avoid any misconception that Spring Boot applies them automatically.

### 4.2. Declaring JNDI bindings

**`src/main/resources/jndi.properties`**

```properties
java.naming.factory.initial=org.apache.activemq.artemis.jndi.ActiveMQInitialContextFactory

# Part after "queue." is the JNDI name; value on the right is the Queue on the broker:
queue.jms/Orders=orders.queue

# Additional Topic example to show naming; the runnable demo only uses Queue:
topic.jms/OrderEvents=orders.events
```

Artemis provides `ActiveMQInitialContextFactory` in client JNDI. When `InitialContext` is created, it locates JNDI configuration on the classpath and registers the alias `jms/Orders` to look up a JMS `Queue` pointing to `orders.queue`. For Topics, `topic.jms/OrderEvents=orders.events` is an independent mapping.

**Important version note:** the Java code uses `jakarta.jms.*`, so you must use the compatible Artemis **Jakarta client** (managed by the Boot starter above). Do not mix legacy `javax.jms` artifacts with `jakarta.jms.Queue` types and expect casts to succeed.

**`src/main/resources/application.properties`**

```properties
app.jms.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
app.jms.username=${JMS_USERNAME}
app.jms.password=${JMS_PASSWORD}
```

This file defines three **application-defined** properties to supply details to the provider connection factory. You must pass valid username/password values before starting; placeholders without defaults prevent accidentally using credentials from the wrong environment.

### 4.3. Wiring one JndiDestinationResolver to both sender and listener

**`src/main/java/example/jndi/JmsConfiguration.java`**

```java
package example.jndi;

import jakarta.jms.ConnectionFactory;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JndiDestinationResolver;

@Configuration(proxyBeanMethods = false)
@EnableJms
public class JmsConfiguration {

    @Bean(destroyMethod = "close")
    ActiveMQConnectionFactory connectionFactory(
            @Value("${app.jms.broker-url}") String url,
            @Value("${app.jms.username}") String username,
            @Value("${app.jms.password}") String password) {

        return new ActiveMQConnectionFactory(url, username, password);
    }

    @Bean
    JndiDestinationResolver jndiDestinationResolver() {
        var resolver = new JndiDestinationResolver();
        resolver.setResourceRef(false); // Client-side JNDI alias; do not prepend java:comp/env/
        resolver.setCache(true);
        resolver.setFallbackToDynamicDestination(false);
        return resolver;
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory,
                            JndiDestinationResolver resolver) {
        var template = new JmsTemplate(connectionFactory);
        template.setDestinationResolver(resolver);
        template.setPubSubDomain(false); // Expect Queue.
        return template;
    }

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            JndiDestinationResolver resolver) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setDestinationResolver(resolver);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-2");
        return factory;
    }
}
```

**Detailed explanation:**

1. `connectionFactory()` creates the Artemis implementation using the broker address and credentials. Spring manages this bean and calls `close()` when the application context shuts down. Creating the bean does not guarantee that a TCP connection has already been opened.
2. `jndiDestinationResolver()` creates the singleton resolver. Because `jndi.properties` is on the classpath, the JNDI provider is found via the default `InitialContext`; no manual `Properties` need to be passed to the bean in this example.
3. `setResourceRef(false)` keeps the alias `jms/Orders` as-is; it **does not** prepend `java:comp/env/`.
4. `setFallbackToDynamicDestination(false)` requires a valid JNDI alias. If `queue.jms/Orders` is missing, the error surfaces at resolution time.
5. `JmsTemplate` translates `"jms/Orders"` via the resolver. If you forget `template.setDestinationResolver(resolver)`, the template defaults to dynamic resolution and may target the wrong Queue.
6. **Listeners do not inherit the resolver from JmsTemplate.** Because `@JmsListener` uses a separate listener container, `factory.setDestinationResolver(resolver)` is required. If omitted, the listener may treat `"jms/Orders"` as a broker Queue name instead of doing a JNDI lookup.
7. `@EnableJms` activates `@JmsListener` infrastructure. A bean named `jmsListenerContainerFactory` is discovered by convention when an endpoint does not declare `containerFactory`.
8. `setSessionTransacted(true)` creates a local JMS transaction on the consumer side. If the listener finishes successfully, the container commits; if an exception escapes, the container rolls back and the broker may redeliver. A JMS transaction is **not automatically atomic** with a database transaction.
9. `setConcurrency("1-2")` illustrates one to two consumers, so message processing can run concurrently. Projects requiring strict ordering may choose concurrency 1 or apply partitioning/grouping by business key.

In Spring Boot, defining your own `ConnectionFactory` or `JmsTemplate` bean may cause the corresponding auto-configuration to **back off**. That is normal behavior to avoid duplicate beans; do not add extra factories/templates for the same role without clarifying which bean gets injected.

### 4.4. Publisher and consumer using the JNDI name

**`src/main/java/example/jndi/JndiOrderApplication.java`**

```java
package example.jndi;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JndiOrderApplication {

    private static final String ORDER_DESTINATION = "jms/Orders";

    public static void main(String[] args) {
        SpringApplication.run(JndiOrderApplication.class, args);
    }

    @Bean
    ApplicationRunner samplePublisher(JmsTemplate template) {
        return args -> {
            template.convertAndSend(ORDER_DESTINATION, "order-001");
            System.out.println("sent=order-001");
        };
    }

    @Component
    static class OrderReceiver {
        @JmsListener(destination = ORDER_DESTINATION)
        public void receive(String body) {
            System.out.println("received=" + body);
        }
    }
}
```

`@SpringBootApplication` is placed in package `example.jndi` so Spring scans both `JmsConfiguration` and `OrderReceiver`. `ApplicationRunner` sends a message after the context is initialized. The listener uses the same logical JNDI name. Producer and consumer do not need to hardcode `orders.queue` in Java.

**Expected processing flow:**

```text
ApplicationRunner
   -> JmsTemplate.convertAndSend("jms/Orders", "order-001")
       -> JndiDestinationResolver
          -> JNDI lookup("jms/Orders")
          -> Queue pointing to "orders.queue"
       -> JMS producer sends to broker
   -> prints "sent=order-001"

@JmsListener(destination="jms/Orders")
   -> DefaultJmsListenerContainerFactory
      -> same JndiDestinationResolver
      -> Queue pointing to "orders.queue"
   -> receives TextMessage from broker
   -> prints "received=order-001"
```

Note: **the JNDI alias is resolved on the client side before JMS send/receive**. After resolution, the broker sees the routing/destination according to the JMS implementation, and does not necessarily have any concept of the JNDI name `jms/Orders`.

### 4.5. Run command and stdout

Example using PowerShell (Windows):

```powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "dev-user"
$env:JMS_PASSWORD = "dev-password"

mvn spring-boot:run
```

Replace `dev-user` / `dev-password` with the account provided by your actual broker. On a POSIX shell:

```bash
JMS_BROKER_URL=tcp://localhost:61616 \
JMS_USERNAME=dev-user \
JMS_PASSWORD=dev-password \
mvn spring-boot:run
```

If the broker is running, permissions on the Queue are granted, and no other consumer picks up the message first, the log will show **two lines explicitly printed by the application**:

```text
sent=order-001
received=order-001
```

The order of the two lines is **not fixed**, because the listener runs on another thread and may receive the message before the publisher finishes printing. The application also outputs Spring/JMS startup logs. Each restart causes `ApplicationRunner` to create another message with payload `order-001`; that is a new message, not evidence of broker redelivery. If another process is consuming from the same Queue, `received=...` may appear in that process instead of this application.

**If there is no broker:** the code can compile, but sending/receiving will fail; this is an integration example and requires an actual broker. Do not assert that a single successful `convertAndSend` call guarantees exactly-once business processing across all network/transaction failures.

## 5. Direct JNDI lookup: cross-checking with the resolver

When you need to verify wiring, you can use the native Java JNDI API:

```java
import javax.naming.Context;
import javax.naming.InitialContext;
import javax.naming.NamingException;
import jakarta.jms.Queue;

public final class JndiQueueProbe {
    public static void main(String[] args) throws NamingException {
        Context context = new InitialContext();
        try {
            Queue queue = (Queue) context.lookup("jms/Orders");
            System.out.println("queue=" + queue.getQueueName());
        } catch (jakarta.jms.JMSException ex) {
            throw new IllegalStateException("Cannot read JMS queue name", ex);
        } finally {
            context.close();
        }
    }
}
```

This is a **logically standalone Java class**, yet it needs the right `jakarta.jms-api`, Artemis Jakarta client, and `jndi.properties` on the runtime classpath; it cannot run on a bare JDK alone. You can place the class into the same Maven project from section 4, though it is not Spring Boot's default `main`. With `queue.jms/Orders=orders.queue`, the expected output (when the JNDI provider returns the right Queue type) is:

```text
queue=orders.queue
```

At the Spring level, `JndiTemplate` eliminates some of the `InitialContext` boilerplate:

```java
import jakarta.jms.Queue;
import org.springframework.jndi.JndiTemplate;

// Example inside a bean/service that already has JndiTemplate.
Queue queue = jndiTemplate.lookup("jms/Orders", Queue.class);
String actualQueueName = queue.getQueueName();
```

This is a **snippet**; `NamingException` and `JMSException` must be handled per actual method signatures. `JndiTemplate` is a general-purpose helper for any JNDI object. `JndiDestinationResolver` specializes in accepting destination name strings under the **Spring JMS** contract and returning a matching `Destination`, making it the natural choice for `JmsTemplate` and listener containers.

### 5.1. Looking up ConnectionFactory as an administered object

Not only Destinations, an application server can also publish `ConnectionFactory`, for example:

```text
java:comp/env/jms/ConnectionFactory
```

Then Spring configuration can look up the factory instead of instantiating a provider class directly:

```java
@Bean
jakarta.jms.ConnectionFactory connectionFactory(
        org.springframework.jndi.JndiTemplate jndi) throws javax.naming.NamingException {

    return jndi.lookup(
            "java:comp/env/jms/ConnectionFactory",
            jakarta.jms.ConnectionFactory.class);
}
```

This is a **replacement snippet** for `connectionFactory()` in section 4; do not keep both beans with the same name simultaneously. When the application server provides the factory, let the **container own the lifecycle of the resource it manages**; do not blindly call `close()` on a singleton looked-up factory. Connections/sessions created by application code still need to be released per the corresponding API/conventions.

Separate two concerns: **ConnectionFactory lookup** is connection-level configuration; **Destination lookup via `JndiDestinationResolver`** configures send/receive target names. An application can use JNDI for either one or both.

## 6. Configuration in Jakarta EE / application servers

Most systems deploying Spring into an application server do not construct a client-side `ActiveMQInitialContextFactory` like the Artemis example. Instead, the server exposes resources in the application's **environment naming context (ENC)**, such as `java:comp/env/jms/Orders` and `java:comp/env/jms/ConnectionFactory`.

**JavaConfig example for that environment (replacing the JNDI configuration in section 4):**

```java
@Bean
org.springframework.jms.support.destination.JndiDestinationResolver destinationResolver() {
    var resolver =
            new org.springframework.jms.support.destination.JndiDestinationResolver();
    resolver.setResourceRef(true);
    resolver.setCache(true);
    resolver.setFallbackToDynamicDestination(false);
    return resolver;
}
```

When a service asks for `"jms/Orders"`, Spring can look up `java:comp/env/jms/Orders`. The actual object is allocated and mapped by the server; resource-binding files, permissions, and names depend on WildFly/Payara/TomEE or the active container. A relative resource reference named `jms/Orders` in the application is typically mapped by the server to a JMS resource provisioned by an administrator.

If an organization uses a **remote JNDI provider**, configuring `InitialContext` usually requires provider-specific properties such as factory class, provider URL, and JNDI authentication method (distinct from JMS broker authentication):

```java
Properties env = new Properties();
env.put(javax.naming.Context.INITIAL_CONTEXT_FACTORY,
        "com.example.naming.CustomInitialContextFactory");
env.put(javax.naming.Context.PROVIDER_URL, "iiop://naming.example:2809");

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setJndiEnvironment(env);
resolver.setResourceRef(false);
```

This is **illustrative pseudo-configuration**; `com.example...` is not a real provider and not a runnable standalone program. Replace the factory class, URL, and security settings with your environment's official parameters; do not copy those placeholders into production. Do not put secret JNDI credentials in source code, especially when the naming service is accessed over a network.

## 7. Queue and Topic: the JNDI name does not determine the messaging model

Suppose there are two bindings:

```properties
queue.jms/Orders=orders.queue
topic.jms/OrderEvents=orders.events
```

On the client:

- `jms/Orders` is looked up as a `jakarta.jms.Queue`.
- `jms/OrderEvents` is looked up as a `jakarta.jms.Topic`.

With a `JmsTemplate` configured with `setPubSubDomain(false)`, we send to the Queue using:

```java
queueTemplate.convertAndSend("jms/Orders", "order-created");
```

To send to the Topic, you need a template/endpoint matching `pubSubDomain=true`:

```java
JmsTemplate topicTemplate = new JmsTemplate(connectionFactory);
topicTemplate.setDestinationResolver(jndiDestinationResolver);
topicTemplate.setPubSubDomain(true);
topicTemplate.convertAndSend("jms/OrderEvents", "order-created");
```

Both snippets are **fragments inside code that already has the corresponding beans**, not standalone files. Never create a single `JmsTemplate` singleton and repeatedly flip `pubSubDomain` per request across concurrent threads. Register **two statically configured beans** when both Queue and Topic are needed.

If a template expects a Queue while JNDI returns a Topic, `JndiDestinationResolver` checks destination type compatibility and may raise an error. Enabling `fallbackToDynamicDestination` is not the way to fix this kind of mapping mismatch: declare the right binding and client domain instead.

For `@JmsListener`, configure a separate listener container if listening to a Topic, and choose the subscription mode (durable/non-durable/shared) per business requirements. Changing a JNDI name alone does not establish broadcast semantics to multiple subscribers.

## 8. Why is JndiDestinationResolver useful?

Not every JMS application needs JNDI. When operating across multiple environments or application servers, JNDI helps **decouple logical names in code from provider configuration**.

| Criterion | `DynamicDestinationResolver` | `JndiDestinationResolver` |
| --- | --- | --- |
| Input `"orders.queue"` | Interpreted as a provider destination name for the active Queue/Topic | Interpreted as a JNDI name to look up |
| Depends on JNDI registry | No | Yes |
| Mapping managed outside code | Usually via string properties or app convention | Via JNDI bindings managed by provider/server/admin |
| When name is not found | Provider may create destination object; broker policy decides real behavior | Fails lookup by default; fallback can be enabled |
| Caching resolved Destination | No equivalent JNDI caching mechanism | Yes; `cache=true` by default |
| Best suited for | Small apps, Queue names configured directly | Jakarta EE, multi-profile environments, admin-supplied JMS resources |

**Real-world scenario:** An order service needs to send messages to a partner's Queue. In test, the JNDI binding `jms/Orders` points to `integration-test.orders`; in production, it points to `partner.orders.production`. The service still calls `jmsTemplate.convertAndSend("jms/Orders", order)`. Switching environments lives in naming/broker configuration and the release process, without forcing the service to change strings or recompile.

**Limitation:** If code depends on a specific naming provider, context configuration and JNDI access permissions can still vary between environments. JNDI does not eliminate vendor dependencies completely; it provides a uniform lookup interface to isolate them.

## 9. Cache, reconnect, and binding changes in live environments

A processing pipeline must distinguish **three types of caches/lifecycles**:

1. **Destination cache:** `JndiDestinationResolver` holds `Destination` objects keyed by JNDI alias.
2. **JMS connection/session cache or pool:** controlled by `CachingConnectionFactory`, provider pools, or the application server. These are network/transaction resources, **distinct from the Destination cache**.
3. **Listener container lifecycle:** the listener initializes consumers, recovers connections, and may re-look up destinations on restart. It does not automatically sync every JNDI change in real time.

Therefore, when an admin rebinds `jms/Orders`:
- Decide **when** producers/consumers are permitted to switch to the new Queue so in-flight messages are not lost.
- Disabling caching or calling `clearCache()` lets subsequent lookups pick up the new binding, yet **existing listeners** may still hold consumers on the old destination until the container recreates them.
- If the old Queue/broker still has messages, plan how to drain/retire it; changing a binding does not migrate existing messages from one broker to another.
- Losing the broker does not mean the JNDI alias is wrong. A successfully looked-up `Queue` can still fail to work due to network issues, missing permissions, or the Queue being removed on the broker.

Do not clear the cache on every send "just to stay up to date": that negates caching benefits, makes every request depend on the naming provider, and can increase latency.

## 10. Common errors and how to diagnose them

| Symptom | Likely cause | How to verify / fix |
| --- | --- | --- |
| `NoInitialContextException` or missing initial factory | Missing `jndi.properties` or `java.naming.factory.initial` setting | Check resource on runtime classpath, class name, and provider dependency. |
| `ClassNotFoundException` for Artemis JNDI factory | Missing Artemis client or mixing old Jakarta/JMS versions | Use the right Jakarta client/BOM, inspect dependency tree. |
| `NameNotFoundException` when looking up `jms/Orders` | Missing JNDI alias, wrong namespace, or `resourceRef` | Read exact binding configuration, distinguish `jms/Orders` from `java:comp/env/jms/Orders`. |
| Lookup returns wrong type | Bound as Topic while service expects Queue (or vice versa) | Check `Queue`/`Topic` type and `pubSubDomain`. |
| Publisher sends successfully but listener receives nothing | Two sides use different resolvers, different Queues, or another consumer competes | Check both `JmsTemplate` and `jmsListenerContainerFactory`; inspect actual Queue and broker metrics. |
| `JNDI lookup` succeeds but send fails | Broker offline, wrong URL, auth/permissions, missing physical Queue | Test broker and send/receive permissions independently of JNDI lookup. |
| Messages go into a Queue named `jms/Orders` instead of `orders.queue` | Using default dynamic resolver or fallback hiding an error | Attach `JndiDestinationResolver` properly, disable fallback, and inspect bindings. |
| Just changed JNDI alias yet app still uses old Queue | Destination cache / listener still holding old consumer | Use `removeFromCache` / `clearCache` appropriately; schedule listener restart/rebind operationally. |
| `javax.jms.Queue` cannot be cast to `jakarta.jms.Queue` | Major JMS API/provider mismatch | Align Spring Framework 6.x with Jakarta JMS 3.x / Artemis Jakarta client. |
| Listener logs continuous retries on startup | JNDI resolution or broker not ready | Inspect root exception, listener container logs, Queue name, connectivity, and permissions. |
| Enabling fallback "stops the error" but messages disappear | Fallback created an object pointing to an unintended name | Restore standard binding; inspect actual queue address/routing, DLQ, and auto-create policy. |

### Ordered diagnostic procedure

1. **Check the name:** does code use `jms/Orders` or `orders.queue`? Determine whether it is a JNDI name or a broker Queue name.
2. **Lookup independently:** with the same JNDI provider, call `InitialContext.lookup("jms/Orders")`; verify the object's actual class and `Queue.getQueueName()`.
3. **Check domain:** if a Queue is expected, the object must be a `Queue` and template/listener must set `pubSubDomain=false`.
4. **Check wiring:** do both sender and consumer actually use the same `JndiDestinationResolver` or matching resolvers?
5. **Check broker:** connectivity, address/queue existence, send/consume permissions, routing, backlog, consumer count, and in-flight messages.
6. **Check cache and lifecycle:** if a binding recently changed, inspect resolver cache, listener restart, and rollout policy.
7. **Check transactions:** with transacted listeners, messages may redeliver when the callback throws. Do not treat duplicate processing logs as proof of two Queues.
8. **Check environment isolation:** test and production may use the same alias mapped to different Queues; inspect the actual deployed mapping before resending messages.

## 11. Security, testing, and operational notes

### Do not treat JNDI as a security mechanism

A JNDI name can abstract a resource, yet real permissions reside at the **naming provider** and the **JMS broker/application server**. A user permitted to look up a Queue does not necessarily have permission to send or receive. Conversely, a wrong alias can route messages to an unintended target when fallback is enabled.

- Never embed JNDI/JMS passwords in source code, committed files, or logs. Use secret stores, environment variables, or server resource bindings.
- If the JNDI provider is remote, authentication, connection security/TLS, and classloading trust policies must follow provider guidelines; avoid connecting to untrusted naming servers.
- Assign send/receive and Queue administration permissions per service; test permission failures using accounts resembling production.
- Use distinct, auditable JNDI names for Queues/Topics, never sharing a single name across both destination types when caching is enabled.
- Measure lookup latency, cache hits, naming errors, broker availability, pending/in-flight counts, redeliveries, and DLQs separately to avoid misdiagnosing the wrong layer.

### A practical test suite

| Test case | Expectation |
| --- | --- |
| Lookup valid binding `jms/Orders` | Returns matching `Queue`, `getQueueName()` matches configured Queue. |
| Lookup invalid `jms/Orderz`, fallback disabled | Reports resolution error, does not silently create a new Queue. |
| Bind `jms/Orders` as `Topic` while caller expects Queue | Detects type mismatch. |
| Send via template and receive via listener with same resolver | Message reaches actual Queue, listener processes it when broker/permissions are valid. |
| Configure resolver only on template | Verify listener gets wrong resolution to demonstrate the necessity of configuring both. |
| Rebind alias while `cache=true` | Reproduce stale cache condition; verify appropriate clear/restart. |
| Broker offline, JNDI alias still exists | Lookup may still succeed while send/receive fail; logs distinguish naming vs transport. |
| Retry/redelivery when listener throws | Verify JMS transaction and idempotency; do not conflate with naming errors. |

In unit tests, `JndiTemplate` can be replaced with a mock returning `Queue`/`Topic` to verify resolution and types. Integration tests against a real broker are what prove message paths, permissions, and transactions. Do not write tests assuming an "implicitly present" JNDI server in Spring Boot: when running standalone, you must supply a naming implementation such as Artemis client-side JNDI or another provider.

## 12. Self-check questions

**1.** When the application calls `convertAndSend("jms/Orders", payload)`, must the broker necessarily know the name `jms/Orders`?

**No.** The resolver resolves the alias into a `Queue`; the broker works with the destination/routing represented by the provider—in the example, `orders.queue`.

**2.** Why can sending still fail when `queue.jms/Orders=orders.queue` is bound?

Because a client-side binding does not guarantee the broker is running, the physical Queue has been provisioned, send permissions exist, or the connection is valid.

**3.** Why does `@JmsListener(destination="jms/Orders")` not automatically use the resolver set on `JmsTemplate`?

Because the listener has its own container factory and consumer-creation pipeline. You must attach the resolver to the corresponding `DefaultJmsListenerContainerFactory`.

**4.** What bug can `fallbackToDynamicDestination=true` mask?

It can hide typos/missing JNDI bindings by creating a destination object from the wrong string, sometimes sending messages to an unintended Queue.

**5.** Does setting `cache=false` automatically switch all running listeners to the new Queue after a rebind?

**Not guaranteed.** It affects the next resolution. Already-open consumers may need to be recreated, restarted, or coordinated separately.

**6.** When `jakarta.jms` changed namespace, did JNDI become `jakarta.naming`?

**No.** Java JNDI remains `javax.naming`, while the looked-up JMS objects use `jakarta.jms.Queue` / `jakarta.jms.Topic` in Spring 6.x.

## Conclusion

`JndiDestinationResolver` lets Spring JMS treat a **destination name as a JNDI binding** to retrieve a published `Queue` or `Topic` object. It is valuable when an application server or organization administers JMS destinations outside code and wants the same logical name to point to different resources per environment.

To get it right in real applications, configure the resolver on **both JmsTemplate and the listener container**, choose the right JNDI namespace, keep fallback strict when resources are pre-administered, understand caching, and distinguish lookup success from connectivity, routing, and transactions. With standalone Artemis, JNDI is a **client-side** mechanism; configuring an alias does not replace provisioning the Queue on the broker.

## References

- Spring Framework — Using JMS, `DestinationResolver` and JNDI: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework — Annotation-driven JMS listener, configuring `setDestinationResolver`: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework — `JndiDestinationResolver` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html
- Spring Framework — `JndiLocatorSupport` and `resourceRef`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jndi/JndiLocatorSupport.html
- Apache ActiveMQ Artemis — Using JMS / JNDI / administered objects: https://artemis.apache.org/components/artemis/documentation/latest/using-jms
- Apache ActiveMQ Artemis — Client classpath, Jakarta Messaging: https://artemis.apache.org/components/artemis/documentation/latest/client-classpath
- Jakarta Messaging 3.1 — Specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Oracle Java — Naming and Directory Interface (JNDI) API: https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/package-summary.html