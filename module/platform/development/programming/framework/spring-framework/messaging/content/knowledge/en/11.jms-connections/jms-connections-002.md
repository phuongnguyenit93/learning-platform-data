# Looking Up ConnectionFactory and Destination via JNDI

## 1. Where Does JNDI Sit in JMS Connectivity?

JMS requires at least two resources to send or receive messages:

- `ConnectionFactory`: a factory managed by the JMS provider or application server, used to create JMS connections and sessions.
- `Destination`: the target for messages, usually a `Queue` or `Topic`, configured by an administrator on the broker/application server.

In a Jakarta EE environment, these resources are typically declared and bound into JNDI. The application looks up the configured name to obtain the exact server-managed object. As a result, the application does not have to instantiate a connection factory itself or hardcode broker addresses, accounts, or pool settings in source code.

JNDI (Java Naming and Directory Interface) is a naming and object lookup API. JNDI is not a message broker, does not create JMS delivery guarantees, and does not automatically create queues/topics on every provider. It only returns objects already registered in the naming service.

Spring Framework integrates JNDI with JMS through several components:

- `JndiObjectFactoryBean`: looks up a JNDI object and exposes it as a Spring bean.
- `JndiTemplate`: assists with JNDI operations and manages the `Context` lifecycle across lookups.
- `JndiDestinationResolver`: resolves a destination name into a JMS `Destination` by looking it up in JNDI.
- `JmsTemplate`: sends and receives messages using the configured `ConnectionFactory` and `DestinationResolver`.

Distinguish two operations: looking up `ConnectionFactory` is usually performed once to inject into `JmsTemplate` or a listener container; looking up `Destination` can be performed via the resolver whenever the template needs to convert a destination name into a JMS object.

## 2. What Are ConnectionFactory and Destination?

### 2.1. ConnectionFactory

`jakarta.jms.ConnectionFactory` is the standard Jakarta Messaging interface. The actual object is usually supplied by the JMS provider or application server. It may contain endpoint configuration, authentication, pooling, transaction integration, and connection policies.

Applications should obtain the environment-managed factory when running inside an application server. A server-managed factory can integrate with pooling, credential mapping, and the transaction manager. Creating a separate factory inside the application may bypass those mechanisms or open unnecessary connections.

Spring `JmsTemplate` accepts a `ConnectionFactory` via constructor or property. The template manages creating and releasing the JMS resources used per operation. In a server environment, the factory usually already provides pooling or appropriate connection sharing; do not manually close the `ConnectionFactory` object after sending a message.

### 2.2. Destination, Queue, and Topic

`jakarta.jms.Destination` is the message target abstraction. Two common types are:

- `Queue`: point-to-point model; one message is delivered to one consumer among competing consumers according to provider semantics.
- `Topic`: publish-subscribe model; messages can be distributed to multiple subscriptions depending on configuration and subscription state.

A destination can be created dynamically via `Session.createQueue(...)` or `Session.createTopic(...)`, or pre-administered on the broker and bound into JNDI. For an administered destination, lookup returns a provider-created object that may carry specific settings such as access permissions, durable subscriptions, dead-letter policies, or resource limits.

Do not treat the JNDI name as the broker queue name in all cases. A JNDI name is an alias in the naming service; the physical destination name may differ and is mapped by the provider.

## 3. JNDI Naming and Common Namespaces

JNDI names depend on the deployment environment. In Jakarta EE, common namespaces include:

| Namespace | Scope | Example |
| --- | --- | --- |
| `java:comp/env` | Environment of the running component/module | `java:comp/env/jms/AppConnectionFactory` |
| `java:module` | Module scope | `java:module/env/...` or server-specific resource binding |
| `java:app` | Application scope | `java:app/...` |
| `java:global` | Server-wide scope | `java:global/...` |

Many application servers also have their own JNDI names for global resources. Names like `java:/JmsXA` or `java:jboss/...` are conventions of specific servers, not portable names across all environments.

Examples in this lesson use relative names `jms/AppConnectionFactory` and `jms/Orders` in the component environment. When `resourceRef=true` is enabled, Spring prepends the `java:comp/env/` prefix to relative names. Thus the two names above are looked up respectively as:

~~~text
java:comp/env/jms/AppConnectionFactory
java:comp/env/jms/Orders
~~~

If a full name starting with `java:` is provided, Spring keeps that name as is. Verify the exact resource name the application server actually binds and align the name with deployment configuration.

## 4. Looking Up ConnectionFactory with JndiObjectFactoryBean

`org.springframework.jndi.JndiObjectFactoryBean` is a `FactoryBean` used to look up an object from JNDI and expose the found object in the Spring container. Important properties:

| Property | Meaning |
| --- | --- |
| `jndiName` | Name of the object to look up |
| `expectedType` | Expected type; Spring checks whether the looked-up object is assignable to this type |
| `resourceRef` | Automatically prepends `java:comp/env/` to relative names |
| `lookupOnStartup` | Looks up when Spring initializes the bean; defaults to `true` |
| `cache` | Caches the looked-up object; defaults to `true` |
| `proxyInterface` / `proxyInterfaces` | Interface(s) used to create a proxy when lookup is deferred or uncached |

XML configuration example:

~~~xml
<bean id="jmsConnectionFactory"
      class="org.springframework.jndi.JndiObjectFactoryBean">
    <property name="jndiName" value="jms/AppConnectionFactory"/>
    <property name="resourceRef" value="true"/>
    <property name="expectedType"
              value="jakarta.jms.ConnectionFactory"/>
</bean>
~~~

Spring looks up the object during bean initialization by default and verifies the expected type. Beans needing JMS can inject the product of `jmsConnectionFactory` as a `ConnectionFactory`.

### 4.1. Startup lookup or deferred lookup?

By default, `lookupOnStartup=true` and `cache=true`. The application will fail fast if the resource does not exist or has the wrong type. This is usually the right choice in production because configuration errors are caught immediately at startup.

If the resource appears late or resource redeployment must be supported, you can set `lookupOnStartup=false`. In that case `proxyInterface` or `proxyInterfaces` must be configured, because Spring needs to know the interface to create a proxy before the real object is looked up. `cache=false` causes the object to be looked up again on every proxy access; use it only when the environment genuinely requires that behavior.

Lazy lookup does not make the resource appear on its own. It only delays when the error is detected. If the application needs JMS immediately when serving requests, deferring lookup can cause the failure to surface on the first request.

## 5. Looking Up Destination Directly via JNDI

If there are only a few fixed destinations, each destination can be declared as a Spring bean using `JndiObjectFactoryBean`:

~~~xml
<bean id="ordersQueue"
      class="org.springframework.jndi.JndiObjectFactoryBean">
    <property name="jndiName" value="jms/Orders"/>
    <property name="resourceRef" value="true"/>
    <property name="expectedType" value="jakarta.jms.Queue"/>
</bean>

<bean id="billingTopic"
      class="org.springframework.jndi.JndiObjectFactoryBean">
    <property name="jndiName" value="jms/BillingEvents"/>
    <property name="resourceRef" value="true"/>
    <property name="expectedType" value="jakarta.jms.Topic"/>
</bean>
~~~

The `ordersQueue` bean provides a `Queue`; the `billingTopic` bean provides a `Topic`. You can then inject `Destination`, `Queue`, or `Topic` directly into components. `JmsTemplate.send(Destination, MessageCreator)` accepts a destination object, so it does not need to resolve a name through `DestinationResolver` on each send.

This approach fits when the number of destinations is small, names are stable, and you want to verify them at startup. If there are many destinations or names come from business configuration, using `JndiDestinationResolver` is usually cleaner.

## 6. JndiDestinationResolver and JmsTemplate

`JmsTemplate` accepts a destination name as a `String` and delegates to a `DestinationResolver` to turn that name into a `Destination` object. The default resolver is `DynamicDestinationResolver`: it uses a JMS `Session` to create a destination dynamically by name.

When destination names are administered and bound in JNDI, configure `JndiDestinationResolver`. This resolver:

- Looks up destinations by JNDI name.
- Caches results by name; caching is enabled by default.
- Can clear a single entry or the whole cache via `removeFromCache(...)` and `clearCache()`.
- Does not fall back to creating dynamic destinations by default when lookup fails.

XML configuration example:

~~~xml
<bean id="jndiDestinationResolver"
      class="org.springframework.jms.support.destination.JndiDestinationResolver">
    <property name="resourceRef" value="true"/>
    <property name="cache" value="true"/>
    <property name="fallbackToDynamicDestination" value="false"/>
</bean>

<bean id="jmsTemplate" class="org.springframework.jms.core.JmsTemplate">
    <constructor-arg ref="jmsConnectionFactory"/>
    <property name="destinationResolver" ref="jndiDestinationResolver"/>
</bean>
~~~

In code, you can send to a relative name:

~~~java
jmsTemplate.send("jms/Orders", session ->
        session.createTextMessage("OrderPlaced: ORD-2048"));
~~~

With `resourceRef=true`, the resolver looks up `java:comp/env/jms/Orders`. If you want to use a full name, pass the full name matching the server's binding.

### 6.1. Why should fallback be disabled by default?

If a JNDI lookup fails due to a typo or missing configuration, falling back to `DynamicDestinationResolver` could cause the provider to create a dynamic destination instead of reporting a configuration error. This can result in messages being sent to a different queue/topic or an unintended destination.

Only enable `fallbackToDynamicDestination=true` when the system intentionally allows dynamic destination creation and has proper naming rules, creation permissions, cleanup, and monitoring in place. For administrator-declared destinations, keep fallback disabled so `NameNotFound` errors are surfaced clearly.

### 6.2. Caching destinations

Caching reduces lookup count and avoids repeating naming work for stable destinations. If the provider deletes or replaces a destination, the cached object may no longer be valid. When errors occur due to a changed destination, you can remove the corresponding entry from the cache and look it up again according to your recovery policy.

Do not disable caching just to "always fetch fresh" without understanding the cost and the provider's object lifecycle. If dynamic fallback is enabled, use distinct names across queues and topics because the resolver caches by destination name.

## 7. Configuring the JNDI Environment for Remote Lookup

Inside an application server, the JNDI context is usually provided by the environment. For standalone applications or remote naming services, the application may need to configure the JNDI environment, for example:

- `java.naming.factory.initial`: class name of the provider's `InitialContextFactory`.
- `java.naming.provider.url`: address of the naming service.
- `java.naming.security.principal`: principal used for authentication.
- `java.naming.security.credentials`: corresponding credential.

These are standard JNDI properties, though specific values and client libraries depend on the provider. Spring lets you set the environment via `JndiTemplate` or components extending `JndiAccessor`, such as `JndiObjectFactoryBean` and `JndiDestinationResolver`.

Do not hardcode passwords in source code, committed XML, or logs. Read credentials from a secret store or the environment's secure configuration mechanism. Remote JNDI requires TLS, authentication, and lookup permissions per provider guidance; expose naming ports to untrusted networks only when appropriate controls are in place.

Do not use a generic remote JNDI configuration across all application servers. A provider may require specific client libraries, URLs, truststores, authentication mechanisms, and resource names. Consult documentation for the exact server/broker version.

## 8. JndiTemplate and Manual Lookup

`JndiTemplate` is a Spring utility for performing JNDI operations without repeating `Context` creation and closing. It is suitable when conditional lookup is needed or when writing a small adapter instead of declaring `JndiObjectFactoryBean`.

Example of type-checked lookup:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Queue;

import org.springframework.jndi.JndiTemplate;

public final class JmsResources {
    private final JndiTemplate jndiTemplate;

    public JmsResources(JndiTemplate jndiTemplate) {
        this.jndiTemplate = jndiTemplate;
    }

    public ConnectionFactory connectionFactory() {
        return this.jndiTemplate.lookup(
                "java:comp/env/jms/AppConnectionFactory",
                ConnectionFactory.class);
    }

    public Queue ordersQueue() {
        return this.jndiTemplate.lookup(
                "java:comp/env/jms/Orders",
                Queue.class);
    }
}
~~~

Typed lookup helps detect early when a bound object does not match the expected interface. `JndiTemplate` manages the `Context` used for the lookup operation; the returned JMS object remains managed by the server/provider. Do not close `ConnectionFactory` or `Queue` merely because the lookup completed.

In typical Spring applications, `JndiObjectFactoryBean` is more convenient because it brings the resource into dependency injection and supports caching and lazy proxies. Use `JndiTemplate` when dynamic lookup logic is needed or when you want to handle multiple names with custom rules.

## 9. Integration Example: Java 17 + Spring Framework 6.2

The example below configures `ConnectionFactory` and destination via JNDI, then sends a text message using `JmsTemplate`. The example needs to run inside a Jakarta EE/application server or a JMS environment with a naming provider that has bound the corresponding resource names. It cannot run standalone via Maven alone because the JNDI context and JMS provider must be supplied by the deployment environment.

Project structure:

~~~text
jms-jndi-demo/
  pom.xml
  src/main/java/com/example/messaging/JmsJndiConfiguration.java
  src/main/java/com/example/messaging/OrderSender.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-jndi-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
        <jakarta.jms.version>3.1.0</jakarta.jms.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>${jakarta.jms.version}</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/JmsJndiConfiguration.java`:

~~~java
package com.example.messaging;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JndiDestinationResolver;
import org.springframework.jndi.JndiObjectFactoryBean;

@Configuration
public class JmsJndiConfiguration {

    @Bean
    public JndiObjectFactoryBean jmsConnectionFactory() {
        JndiObjectFactoryBean factory = new JndiObjectFactoryBean();
        factory.setJndiName("jms/AppConnectionFactory");
        factory.setResourceRef(true);
        factory.setExpectedType(ConnectionFactory.class);
        return factory;
    }

    @Bean
    public JndiDestinationResolver jndiDestinationResolver() {
        JndiDestinationResolver resolver = new JndiDestinationResolver();
        resolver.setResourceRef(true);
        resolver.setCache(true);
        resolver.setFallbackToDynamicDestination(false);
        return resolver;
    }

    @Bean
    public JmsTemplate jmsTemplate(
            ConnectionFactory jmsConnectionFactory,
            JndiDestinationResolver jndiDestinationResolver) {
        JmsTemplate template = new JmsTemplate(jmsConnectionFactory);
        template.setDestinationResolver(jndiDestinationResolver);
        return template;
    }
}
~~~

`src/main/java/com/example/messaging/OrderSender.java`:

~~~java
package com.example.messaging;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderSender {
    private final JmsTemplate jmsTemplate;

    public OrderSender(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void sendOrderPlaced(String orderId) {
        this.jmsTemplate.send("jms/Orders", session -> {
            var message = session.createTextMessage("OrderPlaced: " + orderId);
            message.setStringProperty("eventType", "OrderPlaced");
            return message;
        });
    }
}
~~~

Deploy this configuration in a Spring application context and call `sendOrderPlaced("ORD-2048")` after the server has bound:

- `jms/AppConnectionFactory` to a Jakarta JMS `ConnectionFactory`.
- `jms/Orders` to a JMS `Queue` administered on the provider.

Because `resourceRef=true`, Spring looks up the corresponding names under `java:comp/env/`. `JmsTemplate` uses the looked-up factory and `JndiDestinationResolver` to locate the queue. `send()` creates a `TextMessage` using the `Session` provided by the template; the template manages using and releasing JMS resources.

There is no fixed stdout for this integration example: output depends on the broker, acknowledgement configuration, and server logging. A successful `send()` call only reflects sending according to the JMS provider's semantics; to verify that a consumer processed the message, observe the consumer side or use an appropriate acknowledgement/response.

## 10. Lifecycle and Resource Management

JNDI lookups and JMS resources have different lifecycles:

- `Context`: naming context used for lookups; `JndiTemplate` manages creating and closing the context for lookup operations.
- `ConnectionFactory`: resource managed by the provider/server; the application usually holds a reference and injects it into templates/containers.
- `Destination`: object representing the JMS target; not a connection or session, and usually cached/referenced in the application.
- `Connection`, `Session`, `MessageProducer`, `MessageConsumer`: JMS communication resources; let `JmsTemplate` or listener containers manage their lifecycle according to contract.

Do not create a `Connection`/`Session` shared across multiple threads. JMS `Session` is not thread-safe by contract; let Spring templates/containers create and manage sessions per operation or consumer thread. Do not close resources managed by an application server if the provider documentation specifies that the container owns the lifecycle.

For standalone applications, you can use `SingleConnectionFactory` to share a connection and create separate sessions per operation, or use a provider-supplied pool. In an application server, prefer the server-managed connection factory and configured pooling/transactions.

## 11. Common Errors and Diagnostics

| Error | Possible cause | How to check |
| --- | --- | --- |
| `NoInitialContextException` | No JNDI provider/context factory or missing environment configuration | Check the application server, provider client library, and `java.naming.factory.initial` |
| `NameNotFoundException` | Wrong name or resource not yet bound | Check the exact namespace, resource name, and deployment configuration |
| `ClassCastException` / wrong `expectedType` | Lookup returned an object of a different type than expected | Confirm the resource binding is `ConnectionFactory`, `Queue`, or `Topic` |
| `DestinationResolutionException` | `JndiDestinationResolver` could not find the destination | Check JNDI name, `resourceRef`, and provider bindings |
| `JMSException` on send | Broker disconnected, send permission denied, or invalid destination | Check provider logs, connection factory, permissions, and broker status |
| Send succeeds but consumer does not receive | Wrong queue/topic, subscription, selector, durable subscription, or consumer not running | Check physical destination, consumer binding, and subscription configuration |
| Application fails to start | `JndiObjectFactoryBean` looks up at startup but resource is not ready yet | Check startup order; use lazy lookup only if truly necessary |
| Messages go to an unexpected destination | Wrong JNDI name while dynamic fallback is enabled | Disable fallback or verify dynamic destination creation policy |

In Spring, `JndiObjectFactoryBean` typically translates lookup failures into bean initialization exceptions. `JndiDestinationResolver` throws `DestinationResolutionException` when it cannot resolve a name as configured. Spring JMS also translates many `jakarta.jms.JMSException` instances into unchecked exceptions in Spring's exception hierarchy, helping application code handle errors consistently.

Do not log passwords, credentials, or full environment properties. When reporting errors, log the normalized resource name, expected resource type, application/server, and root cause; mask sensitive information.

## 12. Choosing Between JndiObjectFactoryBean and JndiDestinationResolver

| Requirement | Suitable component |
| --- | --- |
| Obtain a `ConnectionFactory` as a shared dependency | `JndiObjectFactoryBean` |
| Obtain a fixed Queue/Topic and inject it directly | `JndiObjectFactoryBean` with `expectedType` set to `Queue` or `Topic` |
| `JmsTemplate` receives destination names at runtime and needs JNDI lookup | `JndiDestinationResolver` |
| Want to create destinations dynamically from names via a JMS Session | `DynamicDestinationResolver` |
| Need fallback from JNDI to dynamic destination | `JndiDestinationResolver` with `fallbackToDynamicDestination=true`, after evaluating policy |
| Need custom conditional lookup operations | `JndiTemplate` or a dedicated lookup service |

There is no need to create a bean for each destination if there are many of them and names are supplied dynamically. Conversely, with a small set of fixed destinations, direct injection catches name mistakes at startup and makes dependencies explicit.

## 13. Deployment Checklist

1. Has the application server/JMS provider created and bound `ConnectionFactory`?
2. Have Queues/Topics been administered and bound under the right JNDI names?
3. Are the names used component-relative or global/provider-specific?
4. Does `resourceRef` match how the names are declared?
5. Is `expectedType` accurately set to `ConnectionFactory`, `Queue`, `Topic`, or `Destination`?
6. Do `lookupOnStartup` and `cache` fit the resource lifecycle?
7. Has `JmsTemplate` been wired with the right `ConnectionFactory` and `DestinationResolver`?
8. Was dynamic fallback accidentally enabled, masking name errors?
9. Are the provider client library and JNDI environment matching the right version/environment?
10. Are credentials managed with secure secrets/configuration?
11. Are connections/sessions/pools properly managed by the container or Spring?
12. Have missing bindings, wrong types, broker disconnects, and replaced destinations been tested?

## 14. Key Takeaways

JNDI helps look up JMS objects administered by a provider or application server. `ConnectionFactory` is usually looked up once and injected into `JmsTemplate` or a listener container; `Destination` can be injected directly with `JndiObjectFactoryBean` or resolved from a name via `JndiDestinationResolver`. `resourceRef=true` allows using relative names under `java:comp/env/`; global names and server-specific names must follow the target environment. `JmsTemplate` uses `DynamicDestinationResolver` by default, so `JndiDestinationResolver` must be configured when destination names are managed in JNDI. Dynamic fallback is disabled by default so lookup errors do not silently create different destinations. Verify bindings, resource types, caching, security, and JMS lifecycle before deployment.

### References

- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Sending a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html)
- [Spring Framework 6.2 — JndiObjectFactoryBean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jndi/JndiObjectFactoryBean.html)
- [Spring Framework 6.2 — JndiDestinationResolver package documentation](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/destination/package-summary.html)
- [Spring Framework 6.2 — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)