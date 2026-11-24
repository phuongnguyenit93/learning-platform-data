# Migrating from javax.jms to jakarta.jms and Version Compatibility Requirements

When upgrading a JMS application from the Spring Framework 5.x generation to Spring Framework 6.x, a major change is that the Jakarta Messaging package moved from javax.jms to jakarta.jms. This is a class-name and binary-level change, so merely bumping the library version while keeping the old imports is not enough.

For a successful migration, you must align source code, API dependencies, the message broker's client library, Spring Framework or Spring Boot, the JDK, and the deployment environment. This lesson explains compatibility boundaries, highlights the required changes, and walks through verifying the application after migration.

## 1. Why Did javax.jms Change to jakarta.jms?

JMS originally belonged to Java EE and used the javax.jms namespace. After Java EE was transferred to the Eclipse Foundation and evolved under the Jakarta EE name, Jakarta EE 9 performed a top-level namespace change from javax to jakarta for platform APIs.

For messaging:

- Java EE 8 uses JMS 2.0 with the javax.jms package.
- Jakarta EE 9 places Jakarta Messaging 3.0 in the jakarta.jms package.
- Jakarta EE 10 places Jakarta Messaging 3.1 in the jakarta.jms package.

The specification name also changed from Java Message Service (JMS) to Jakarta Messaging, though in everyday conversation many engineering teams still refer to it simply as JMS.

The namespace change does not mean all messaging behavior was redesigned. Jakarta Messaging 3.0 continues the model and behavior corresponding to the previous JMS API, but the Java types have new package names. Because the package is part of a type's identity at the JVM level, javax.jms.Message and jakarta.jms.Message are two distinct types.

The Jakarta EE 9 specification defines the namespace shift as neither source- nor binary-compatible with prior Java EE releases. Consequently, a class compiled against javax.jms does not automatically become compatible with jakarta.jms simply by swapping dependencies at runtime.

## 2. Scope of Changes in Source Code

Common import examples:

| Old API | New API |
|---|---|
| javax.jms.ConnectionFactory | jakarta.jms.ConnectionFactory |
| javax.jms.Connection | jakarta.jms.Connection |
| javax.jms.Session | jakarta.jms.Session |
| javax.jms.Destination | jakarta.jms.Destination |
| javax.jms.Queue | jakarta.jms.Queue |
| javax.jms.Topic | jakarta.jms.Topic |
| javax.jms.Message | jakarta.jms.Message |
| javax.jms.TextMessage | jakarta.jms.TextMessage |
| javax.jms.JMSException | jakarta.jms.JMSException |
| javax.jms.JMSContext | jakarta.jms.JMSContext |
| javax.jms.JMSConsumer | jakarta.jms.JMSConsumer |
| javax.jms.JMSProducer | jakarta.jms.JMSProducer |

Example before migration:

~~~java
import javax.jms.ConnectionFactory;
import javax.jms.JMSContext;
import javax.jms.Message;
import javax.jms.TextMessage;
~~~

After migration:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
~~~

Class names and method names remain unchanged in most cases. Changes are primarily in package imports and dependent artifacts. However, you must recompile all source code and modules that reference the new JMS API.

### Do not mechanically replace every javax package

Not every package starting with javax moved to jakarta. Several packages belong to Java SE and remain unchanged, for example:

- javax.sql.DataSource
- javax.naming.Context
- javax.naming.InitialContext
- javax.crypto.Cipher
- javax.management.MBeanServer
- javax.net.ssl.SSLContext

Other Java EE/Jakarta EE APIs may have changed namespaces, such as javax.servlet to jakarta.servlet, javax.persistence to jakarta.persistence, javax.transaction to jakarta.transaction, and javax.annotation to jakarta.annotation.

When migrating JMS, search specifically for javax.jms across source, tests, configurations, and dependencies. A blanket search-and-replace of javax. with jakarta. can break Java SE APIs that retain the old namespace.

## 3. Relationship Between Spring, JMS API, and Java Versions

Consider Spring and JMS API versions together:

| Generation | Messaging platform | Namespace | Java baseline |
|---|---|---|---|
| Spring Framework 5.3 | JMS 2.0 / Java EE 8 | javax.jms | Depends on Spring 5.3 release and application; supports Java 8+ |
| Spring Framework 6.0 | Jakarta Messaging 3.0+ | jakarta.jms | Java 17+ |
| Spring Framework 6.1 / 6.2 | Jakarta Messaging 3.x | jakarta.jms | Java 17+ |
| Spring Boot 2.7 | Spring Framework 5.3 | javax.jms | Follows Boot 2.7 baseline |
| Spring Boot 3.x | Spring Framework 6.x | jakarta.jms | Java 17+ |

Spring Framework 6.0 raised the baseline to Java 17 and Jakarta EE 9. Spring Boot 3.0 requires Java 17 and Spring Framework 6.0. Spring 6.x lines continue using jakarta.jms.

Jakarta Messaging 3.0 corresponds to Jakarta EE 9; Jakarta Messaging 3.1 corresponds to Jakarta EE 10. The exact API version used by the application must be compatible with the Spring line, provider, and runtime in use. Let the Spring Boot BOM or project dependency management handle versions whenever possible.

The table above is a guide by major generation. When picking a specific patch release, check the release notes and dependency management of your exact Spring Boot/Spring Framework version, as well as the JMS provider's support matrix.

## 4. Maven Dependencies That Must Change

For older JMS applications, the API dependency typically looks like:

~~~xml
<dependency>
    <groupId>javax.jms</groupId>
    <artifactId>javax.jms-api</artifactId>
    <version>2.0.1</version>
</dependency>
~~~

The Jakarta Messaging API dependency looks like:

~~~xml
<dependency>
    <groupId>jakarta.jms</groupId>
    <artifactId>jakarta.jms-api</artifactId>
    <version>3.1.0</version>
</dependency>
~~~

If the application uses Spring Framework 6.x directly, the Spring JMS integration module is spring-jms:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-jms</artifactId>
    <version>6.2.19</version>
</dependency>
~~~

In a Spring Boot application, use the starters and BOM managed by Spring Boot. For example, a Boot app can declare the starter for the provider in use and let dependency management select compatible Spring/Jakarta versions. Do not arbitrarily pin a Jakarta JMS API version if the provider or Spring line requires a different one.

Notes:

- jakarta.jms-api only provides API interfaces and classes. It is not a message broker and does not create a working ConnectionFactory by itself.
- The application needs the provider's client library such as ActiveMQ, Artemis, IBM MQ, Solace, or the corresponding product.
- The provider's client artifact must implement jakarta.jms if the application uses Spring 6.x.
- Do not keep both javax.jms-api and jakarta.jms-api simultaneously just to silence compiler errors. The two APIs are not type-interchangeable and can cause conflicts or confusion in the dependency graph.
- Some providers bundle the API inside their client artifact. Follow the provider's guidance to avoid duplicate API declarations.

## 5. What Changes and What Stays the Same in Spring JMS?

Spring's integration package remains org.springframework.jms. For example:

- org.springframework.jms.core.JmsTemplate
- org.springframework.jms.annotation.JmsListener
- org.springframework.jms.config.DefaultJmsListenerContainerFactory
- org.springframework.jms.support.converter.MessageConverter

These Spring classes did not rename their packages for the Jakarta namespace. What changed is that the JMS types they interact with moved to jakarta.jms.

For example, JmsTemplate is still imported as:

~~~java
import org.springframework.jms.core.JmsTemplate;
~~~

When working directly with the JMS API, use the new types:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;
~~~

If code uses both Spring Message and JMS Message, keep the imports accurate:

- org.springframework.messaging.Message is Spring Messaging's Message abstraction.
- jakarta.jms.Message is the Jakarta Messaging provider's message.

These two types serve two different layers. Mixing up the imports can cause compile errors or incorrect message conversion.

## 6. Code Changes Before and After Migration

### Example sending a message with JMSContext

Before migration:

~~~java
import javax.jms.ConnectionFactory;
import javax.jms.JMSContext;
import javax.jms.Topic;

public class LegacyPublisher {

    public void publish(ConnectionFactory connectionFactory, Topic topic) {
        try (JMSContext context =
                connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            context.createProducer().send(topic, "OrderCreated");
        }
    }
}
~~~

After migration, the send logic does not need to change; switch imports to jakarta.jms:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Topic;

public class JakartaPublisher {

    public void publish(ConnectionFactory connectionFactory, Topic topic) {
        try (JMSContext context =
                connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            context.createProducer().send(topic, "OrderCreated");
        }
    }
}
~~~

The post-migration snippet needs a Jakarta JMS provider supplying a compatible ConnectionFactory and Topic. Having only the API dependency cannot connect to a broker.

### Example listener in Spring

Listeners using Spring annotations remain the same:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(destination = "orders.events")
    public void receive(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

If the listener receives a raw JMS Message directly, the import must be jakarta.jms.Message:

~~~java
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class RawOrderListener {

    @JmsListener(destination = "orders.events")
    public void receive(Message message) throws Exception {
        if (message instanceof TextMessage textMessage) {
            System.out.println(textMessage.getText());
        }
    }
}
~~~

Spring uses MessageConverter to convert the JMS Message into a Java payload when the listener method declares a String or DTO parameter. When the method accepts jakarta.jms.Message directly, the application works with the Jakarta Messaging message.

## 7. Compatibility Requirements with JMS Provider and Broker

Updating imports and dependencies is only part of the migration. The JMS provider must supply a client library compatible with Jakarta Messaging.

Verify four components:

**API:** the application compiles against an appropriate jakarta.jms-api version.

**Provider client:** the broker's client library must implement the jakarta.jms namespace. An older client implementing only javax.jms.ConnectionFactory cannot be passed into code expecting jakarta.jms.ConnectionFactory.

**Broker/server:** the server version must be supported by the provider for the Jakarta client in use. Some brokers allow upgrading clients without upgrading the server; some products require a newer server version or configuration. Check the vendor's official compatibility matrix.

**Runtime/container:** if the application runs inside an application server, the server must provide the matching Jakarta Messaging API and resources. Do not bundle a conflicting API version alongside the server-provided API when the environment expects shared libraries.

Namespace is a Java type name concern, whereas wire protocol and message format are separate concerns. Switching from javax.jms to jakarta.jms does not itself alter JSON payloads, destination names, or the broker's wire protocol. However, whether two client generations can connect to the same broker simultaneously depends on the provider. Do not assume an old JMS client and a new Jakarta client can share Java serialized objects or ConnectionFactory classes.

## 8. Binary Compatibility and Errors When Mixing Two Namespaces

Consider these two types:

~~~java
javax.jms.ConnectionFactory
jakarta.jms.ConnectionFactory
~~~

Although their simple class names are identical, the JVM treats them as two independent types because their fully qualified names differ.

A library compiled against javax.jms may expose method signatures containing javax.jms.Message. Spring 6.x calls the corresponding method with jakarta.jms.Message. The two signatures are incompatible.

Common errors:

- package javax.jms does not exist: the old dependency is no longer on the classpath or has been switched to the Jakarta API.
- package jakarta.jms does not exist: the Jakarta API or a matching provider client has not been declared.
- ClassCastException: code attempts to cast between the two namespaces.
- NoClassDefFoundError: the runtime cannot find a class required by a compiled library.
- NoSuchMethodError or LinkageError: library versions are inconsistent or the same class is loaded from different APIs.
- ClassNotFoundException: old class names remain in configuration, reflection, or metadata.

This cannot be solved by casting, renaming variables, or putting both APIs on the classpath. All components communicating directly via JMS types must be aligned.

## 9. Step-by-Step Migration Process

### Step 1 — Capture the current baseline

Before making changes, record:

- Java version.
- Spring Framework or Spring Boot version.
- JMS API version.
- JMS provider and client library version.
- Broker/server version.
- How ConnectionFactory, Destination, and listener containers are created.
- Active flows for sending, receiving, transactions, acknowledgement, durable subscriptions, and retries.

Run existing tests to establish a baseline.

### Step 2 — Choose the upgrade target

If the application is on Spring Boot 2.7 or Spring Framework 5.3, identify the appropriate Spring Boot 3.x/Spring Framework 6.x line. Spring Framework 6.x requires Java 17 or newer.

Check other integration libraries such as Spring Cloud, Spring Integration, Spring Batch, security, tracing, and provider libraries. Each project has its own release schedule and compatibility requirements.

### Step 3 — Upgrade JDK and Spring dependencies

Upgrade build and runtime environments to JDK 17 or higher when moving to Spring 6. If using Spring Boot, update the parent/BOM or dependency management plugin and let starters manage Spring modules.

Do not upgrade spring-jms alone to a new major version while leaving the rest of the Spring Framework modules on an older line.

### Step 4 — Replace the API namespace

Search for javax.jms references across:

- Main source code.
- Tests and test fixtures.
- Shared modules.
- XML, properties, and YAML configurations.
- Reflection and string-based class names.
- Internal adapters or libraries.

Switch JMS types to jakarta.jms, then recompile all affected modules.

### Step 5 — Upgrade the provider client

Replace the broker client library with a version supporting Jakarta Messaging. Check declarations for ConnectionFactory, JNDI, TLS, authentication, failover, pooling, and destinations.

If the application uses resources provided by an application server, verify that those resources implement the Jakarta Messaging API and can be injected into Spring.

### Step 6 — Inspect the dependency tree

With Maven:

~~~shell
mvn dependency:tree
~~~

You can filter for JMS artifacts:

~~~shell
mvn dependency:tree -Dincludes=javax.jms:javax.jms-api,jakarta.jms:jakarta.jms-api
~~~

The goal is to identify which library is still pulling in the old API. If an internal library still depends on javax.jms, upgrade or recompile that library.

With Gradle, use:

~~~shell
./gradlew dependencies
~~~

and inspect both runtimeClasspath and testRuntimeClasspath.

### Step 7 — Run integration tests against a real broker

Verify at minimum:

- Producer sending TextMessage, BytesMessage, or the message types in use.
- Consumer receiving and converting payloads.
- Selectors and message properties.
- Queue, Topic, and shared/durable subscriptions if used.
- Acknowledgement, session transactions, and rollbacks.
- Redelivery, dead-letter queues, and retries.
- Correlation ID and request/reply.
- Reconnect, failover, and broker restarts.
- TLS, authentication, and destination access permissions.
- Concurrency, shutdown, and graceful recovery.

Testing with a real broker is essential because a successful compile only confirms API and type alignment. It does not prove that the provider client, broker, and operational configuration are compatible.

### Step 8 — Deploy across environments progressively

Run integration tests in dev, staging, and production-like environments. For rolling deployments, verify explicitly whether the broker supports simultaneous old and new clients. If two application versions run concurrently, avoid sharing JMS serialized objects or Java classes across namespaces; exchange messages through the broker using payloads with stable schemas.

Monitor connection failures, authentication errors, message backlogs, redeliveries, consumer counts, and message conversion errors after deployment.

## 10. Runnable Example: Verifying the Jakarta JMS Namespace

The small example below confirms the program compiles against the jakarta.jms API and Spring JMS 6.2.19. It does not connect to a broker, since the goal is compile-time and runtime namespace verification.

Structure:

~~~text
jakarta-jms-check/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── JmsNamespaceCheck.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>jakarta-jms-check</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.19</version>
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

### src/main/java/demo/JmsNamespaceCheck.java

~~~java
package demo;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;

public class JmsNamespaceCheck {

    public static void main(String[] args) {
        System.out.println(ConnectionFactory.class.getName());
        System.out.println(Message.class.getName());
        System.out.println(TextMessage.class.getName());
        System.out.println(JmsTemplate.class.getName());
    }
}
~~~

Run from the directory containing pom.xml:

~~~shell
mvn -q compile exec:java -Dexec.mainClass=demo.JmsNamespaceCheck
~~~

Output:

~~~text
jakarta.jms.ConnectionFactory
jakarta.jms.Message
jakarta.jms.TextMessage
org.springframework.jms.core.JmsTemplate
~~~

The output confirms the source references Jakarta Messaging types and the Spring JMS integration class. To test actual connectivity, add a JMS provider client, configure ConnectionFactory, and run send/receive tests against a broker.

## 11. Using Migration Helper Tools

Several tools can help locate and transform source/dependencies:

**OpenRewrite:** provides migration recipes for Spring Boot and Jakarta EE, assisting with updating package imports, configurations, and dependencies where covered by recipes.

**Spring Boot Migrator:** helps analyze and suggest changes when upgrading Spring Boot applications.

**IntelliJ IDEA:** has built-in features to assist with package and dependency migration.

**Eclipse Transformer:** can transform bytecode, resources, or archives by namespace rules in certain scenarios where a library lacks a Jakarta release.

These tools automate mechanical work. They cannot verify on their own that the JMS provider, broker, transactions, acknowledgement, and failover work properly. Always review diffs, inspect the dependency tree, compile, and run integration tests after transforming.

## 12. Common Mistakes and Misconceptions

**Changing only imports while keeping the old client:** code will fail to compile or the runtime will fail to load Jakarta types. Upgrade the provider client at the same time.

**Changing only dependencies without recompiling:** old bytecode still embeds javax.jms class names. Rebuild all dependent modules.

**Adding both APIs to avoid compile errors:** the two namespaces are separate type sets. An old dependency may be pulled in transitively by another library; locate and resolve that dependency source.

**Replacing all javax with jakarta:** several Java SE packages keep javax, such as javax.sql and javax.naming. Only replace packages that moved per the specification.

**Thinking Spring packages changed too:** org.springframework.jms remains Spring's package. Only the referenced JMS API types moved to jakarta.jms.

**Thinking a namespace change alters the broker protocol:** namespace is a Java type name concern. Protocol compatibility and connectivity depend on the provider client and broker.

**Thinking a successful API compile means migration is complete:** compiling does not test connectivity, access permissions, transactions, acknowledgement, redelivery, durable subscriptions, or failover.

**Upgrading Spring while forgetting Java:** Spring Framework 6.x requires Java 17 or newer. Build JDK and runtime must align.

**Forgetting internal libraries:** a shared module or legacy adapter may still expose javax.jms signatures. Every module interacting directly with JMS must be upgraded or recompiled.

## 13. Pre-Completion Migration Checklist

1. Spring Framework/Boot and JDK are on compatible versions.
2. All JMS imports in source and tests have moved to jakarta.jms.
3. The dependency tree contains no javax.jms-api outside intentionally isolated cases.
4. The JMS provider client supports Jakarta Messaging and is compatible with the broker/server.
5. ConnectionFactory, Destination, JNDI, and security configurations work.
6. Spring JmsTemplate and @JmsListener remain properly configured.
7. MessageConverter handles both old and new payloads properly.
8. Queue, Topic, selectors, and durable/shared subscriptions work properly.
9. Transactions, acknowledgement, rollbacks, redelivery, and DLQ are tested.
10. Request/reply, correlation ID, timeouts, and retries continue working.
11. No ClassNotFoundException, ClassCastException, NoSuchMethodError, or LinkageError occurs.
12. Integration tests pass against a compatible broker in a production-like environment.
13. A mixed old/new client deployment plan exists if rolling deployment is required.

## 14. Takeaways

- javax.jms belongs to the Java EE/JMS 2.0 generation; jakarta.jms belongs to Jakarta Messaging 3.x.
- Jakarta EE 9 introduced the namespace change, which is not source/binary-compatible with legacy Java EE APIs.
- Spring Framework 5.3 uses the javax.jms generation; Spring Framework 6.x uses jakarta.jms and requires Java 17 or newer.
- Spring Boot 2.7 belongs to the Spring 5.3 generation; Spring Boot 3.x belongs to the Spring 6.x and Jakarta generation.
- The Spring package org.springframework.jms stays unchanged; JMS types are imported from jakarta.jms.
- Both API dependencies and a compatible JMS provider client must be upgraded, and the broker/server and runtime verified.
- Do not mechanically replace every javax occurrence because many Java SE packages keep that namespace.
- Compiling cleanly is not enough; test against a real broker for send/receive, transactions, acknowledgement, subscriptions, redelivery, and failover.

## References

- [Jakarta EE 9 Platform Specification — Namespace and backward compatibility](https://jakarta.ee/specifications/platform/9/jakarta-platform-spec-9.html)
- [Jakarta Messaging — Versions 2.0, 3.0, and 3.1](https://jakarta.ee/specifications/messaging/)
- [Spring Framework 6.0 Release Notes — Baseline upgrades](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.0-Release-Notes)
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Framework 6.2 — JMS Integration](https://docs.spring.io/spring-framework/reference/6.2/integration/jms.html)
