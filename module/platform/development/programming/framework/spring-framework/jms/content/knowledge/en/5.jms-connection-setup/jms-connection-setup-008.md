# Plain Spring Framework vs. Spring Boot Auto-Configuration for JMS Connection Setup

**Context:** In a Java application using Jakarta Messaging (JMS), both **plain Spring Framework** and **Spring Boot** can send with `JmsTemplate` and receive with `@JmsListener`. The main difference lies in **who creates the configuration beans and under which rules**. Understanding this boundary helps avoid adding a dependency with no working connection, declaring custom beans that accidentally disable auto-configuration, or running fine in development yet failing transactions/recovery upon deployment.

**Example scope:** Java 17+, Spring Framework 6.1.x, and Spring Boot 3.3.x (Jakarta Messaging, `jakarta.jms` package), with an **external ActiveMQ Artemis broker**. Both deployment paths use the same broker type for comparison. For other Spring Boot/Spring Framework versions, check version-specific docs because auto-configuration conditions and properties may change.

## 1. Same JMS API, Two Ways to Build the Spring Container

Regardless of how you configure it, the core dependency chain stays the same:

~~~text
Application
├─ JMS producer
│    └─ JmsTemplate
│         └─ jakarta.jms.ConnectionFactory ──► JMS client ──► Artemis broker
└─ JMS consumer
     └─ @JmsListener
          └─ JmsListenerContainerFactory
               └─ listener container
                    └─ jakarta.jms.ConnectionFactory ──► Artemis broker
~~~

**Spring Framework** supplies `JmsTemplate`, `@EnableJms`, `DefaultJmsListenerContainerFactory`, listener containers, exception translation, message conversion, destination resolvers, and transaction integration. It **does not decide on its own** that you will connect to Artemis at `tcp://localhost:61616`, which user to use, or what policy a listener container should apply. Adding only `spring-jms` to a plain Spring app does not conjure up a provider-specific `ConnectionFactory`.

**Spring Boot** sits on top of Spring Framework and adds **conditional auto-configuration**. With a JMS starter, a compatible provider client, and `spring.artemis.*` or `spring.activemq.*` properties, Boot can create `ConnectionFactory`, wrap it with caching/pooling, and create `JmsTemplate` plus the default `JmsListenerContainerFactory`. Application-declared beans can still be used; Boot typically **backs off** for beans that already exist. Boot does not invent a new JMS protocol and does not replace the actual broker.

> **Clear distinction:** "Spring Boot auto-configures JMS" means **auto-configuring the Spring-side infrastructure when conditions match**. It does **not** mean the broker, queues, credentials, TLS, HA, ACLs, DLQ, and persistence will be provisioned automatically in production. An embedded broker is a separate capability that only activates with the right dependency/mode; this lesson uses an external broker.

## 2. Comparison Table: Who Is Responsible for What?

| Component / decision | Plain Spring Framework | Spring Boot with Artemis starter |
| --- | --- | --- |
| JMS API and provider | Add `spring-jms`, `jakarta.jms`, and a compatible JMS client yourself | `spring-boot-starter-artemis` brings most compatible dependencies; BOM manages versions |
| Broker endpoint and credentials | Instantiate client `ConnectionFactory` or look up via JNDI yourself | Typically declare `spring.artemis.mode=native`, `broker-url`, `user`, `password` |
| `ConnectionFactory` bean | Declare yourself or import from another configuration | Boot creates it based on classpath/bean conditions and provider |
| Connection/session caching/pooling | Pick a suitable wrapper or pool yourself | Boot wraps in `CachingConnectionFactory` by default; pooling needs separate dependency/properties |
| `JmsTemplate` | Declare `@Bean` yourself, specifying `ConnectionFactory` | Auto-configured when conditions match; inject directly |
| `@JmsListener` | Usually requires `@EnableJms` to enable annotated endpoints | Boot activates listener infrastructure when JMS infrastructure is present; usually no manual `@EnableJms` needed |
| Factory for `@JmsListener` | Create a bean named `jmsListenerContainerFactory` or specify a factory | Boot creates the default factory if no matching bean exists |
| Queue/topic mode | Configure `pubSubDomain` on template and container yourself | `spring.jms.pub-sub-domain` controls the default (queue by default) |
| Listener transaction/ack | Configure `sessionTransacted`, transaction manager, and concurrency yourself | Boot's default factory is configured as transactional; details depend on JTA presence and overrides |
| Message converter and destination resolver | Register and attach to template/listener yourself | Boot can attach converter/resolver beans into auto-configured infrastructure |
| Missing dependencies or bean conflicts | Typically surfaces directly as dependency injection/startup failures | Condition report shows whether auto-config "matched" or "did not match" |
| Complex customization | Full manual control over every bean | Configure properties first; use beans/configurers for what exceeds property scope |

**Technical note:** Plain Spring is not "lower-level than JMS"—both use the exact same `spring-jms` and `jakarta.jms`. Boot mainly reduces repetitive configuration and manages versions. Understanding plain configuration reveals exactly what Boot creates so you avoid accidental overrides.

## 3. Checking Prerequisites Before Writing Code

Verify four groups of conditions:

1. **Java + API:** Spring 6+/Boot 3+ apps use `jakarta.jms.ConnectionFactory` and `jakarta.jms.Message`. Old JMS drivers using only `javax.jms` cannot simply be cast to Jakarta.
2. **JMS provider client:** pick a library compatible with both the broker and the Jakarta API. For Artemis use `artemis-jakarta-client`; avoid pairing legacy `javax.jms` `artemis-jms-client` with Spring 6.
3. **Real broker:** the URL must use a transport the client supports; the broker must have a matching listener/acceptor enabled, network reachability, and valid credentials/permissions.
4. **Destinations and consumption:** queue/topic names, whether auto-create is enabled, security permissions, message TTL/retention, consumer ack/transactions, and DLQ. Constructing a Java `Destination` object does not mean a durable broker resource exists under policy.

### 3.1. Different Dependencies

In **plain Spring**, you manage compatible library versions yourself—at minimum `spring-context`, `spring-jms`, Jakarta JMS API (usually pulled in via Spring/Artemis), and the Artemis Jakarta client. You can use the Spring Framework BOM to manage Spring versions and pin a compatible provider version.

In **Spring Boot**, the minimal dependency for the example is `spring-boot-starter-artemis` alongside the Spring Boot core starter (pulled transitively). Boot's plugin/BOM manages Spring and JMS client versions; do not pin extra `spring-jms` or Artemis versions separately without a clear reason and inspecting the dependency graph.

**Do not infer** that having a `ConnectionFactory` class on the classpath means a `ConnectionFactory` bean is registered. The **classpath** tells Spring which implementation classes are available; **bean definitions** are what get injected into `JmsTemplate`/listeners.

## 4. Example A — Plain Spring Framework: Wiring All JMS Infrastructure Yourself

This is a **Java SE application using Spring `ApplicationContext`**, with no `@SpringBootApplication` and no Boot auto-configuration. The goal is to see every piece you must declare.

### 4.1. `build.gradle`

Standalone illustrative example with Gradle Groovy, Java 17, and released versions. In real projects, choose a version range tested against your broker:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework:spring-framework-bom:6.1.20')
    implementation 'org.springframework:spring-context'
    implementation 'org.springframework:spring-jms'
    implementation 'org.apache.activemq:artemis-jakarta-client:2.42.0'

    runtimeOnly 'org.slf4j:slf4j-simple:2.0.17'
}

application {
    mainClass = 'example.jmsmanual.ManualJmsApp'
}
~~~

Uses the **Jakarta client** with Spring 6. To target longer-supported versions, pick the corresponding Spring/provider pair and run integration tests; do not assume the versions listed above are the latest or a certified production bundle.

### 4.2. Complete Java Code (Single Compilable File)

File `src/main/java/example/jmsmanual/ManualJmsApp.java`:

~~~java
package example.jmsmanual;

import jakarta.jms.ConnectionFactory;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

public final class ManualJmsApp {
    public static void main(String[] args) throws InterruptedException {
        try (var context = new AnnotationConfigApplicationContext(
                ManualJmsConfig.class)) {

            JmsTemplate template = context.getBean(JmsTemplate.class);
            template.convertAndSend("orders.inbox", "order-42");
            System.out.println("Producer sent order-42");

            // Only to observe the listener before the program exits.
            Thread.sleep(3_000L);
        }
    }
}

@Configuration
@EnableJms
class ManualJmsConfig {
    @Bean(destroyMethod = "close")
    ActiveMQConnectionFactory connectionFactory() {
        String url = System.getenv().getOrDefault(
                "JMS_BROKER_URL", "tcp://localhost:61616");
        String user = System.getenv().getOrDefault(
                "JMS_USER", "demo");
        String password = System.getenv("JMS_PASSWORD");

        if (password == null || password.isBlank()) {
            throw new IllegalStateException(
                    "JMS_PASSWORD environment variable is required");
        }
        return new ActiveMQConnectionFactory(url, user, password);
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false); // "orders.inbox" is a queue.
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }

    @Bean
    OrderListener orderListener() {
        return new OrderListener();
    }
}

class OrderListener {
    @JmsListener(destination = "orders.inbox")
    public void onMessage(String body) {
        System.out.println("Consumer received " + body);
    }
}
~~~

**Exact annotation of each bean:**

- `connectionFactory()` creates the **provider-specific** Artemis factory; Spring cannot guess the URL or credentials. `@Bean(destroyMethod = "close")` tells the container to close resources on shutdown.
- `jmsTemplate(...)` feeds the same `ConnectionFactory` into Spring's JMS abstraction. This is the **sending** path; no manual `Connection`/`Session` creation is needed per business method.
- `@EnableJms` turns on `@JmsListener` annotation processing in plain Spring Framework.
- The bean named **`jmsListenerContainerFactory`** is the default factory looked up by annotated endpoint infrastructure. `setConnectionFactory` sets where consumers connect; `setPubSubDomain(false)` selects queue semantics; `setSessionTransacted(true)` ensures listener errors trigger a local JMS rollback rather than silently acknowledging.
- `orderListener()` registers the listener object as a Spring bean. Without `@ComponentScan` in this example, that bean must be declared explicitly.
- `AnnotationConfigApplicationContext` manages bean and container lifecycles; `Thread.sleep` is strictly for demo observation so the app does not exit before receiving the message, **not** a valid message-waiting technique for real systems.

**Prerequisites before running:** an Artemis broker must be listening at the URL, have (or allow auto-creating) queue `orders.inbox`, and accept credentials with send/receive permissions. In your terminal, set `JMS_PASSWORD`, `JMS_USER`, and `JMS_BROKER_URL` for your OS/environment; never hardcode passwords in code. Then run:

~~~bash
./gradlew run
~~~

Sample log output when the broker is ready can include:

~~~text
Producer sent order-42
Consumer received order-42
~~~

**No guarantee of stdout ordering:** the listener runs asynchronously, so the receive log may appear before the send log, or miss the demo window. If the broker is unreachable, `convertAndSend` can throw `JmsException` and no "sent" line will print. Framework/provider logs may also appear.

**Example trade-off:** uses the native `ConnectionFactory` directly for both publisher and listener so the bean graph stays transparent. Under high volume, `JmsTemplate` usually benefits from caching/pooling. When optimizing, configure caching/pooling for the sending path and **keep the native factory for listener containers**, or study wrapper recovery/concurrency closely. We left that out of the demo to keep the core mechanics visible.

## 5. Why Must Example A's Beans Be Present in Plain Spring?

If you omit each piece in Example A:

| Omitted or misdeclared | Observable consequence | Fix |
| --- | --- | --- |
| No Artemis client/provider `ConnectionFactory` | No way to open JMS connections; template/factory missing dependency | Add compatible client and declare `@Bean ConnectionFactory` |
| No `JmsTemplate` bean | Injecting `JmsTemplate` fails if nothing else declares it | Create `new JmsTemplate(connectionFactory)` in `@Bean` |
| Missing `@EnableJms` | `@JmsListener` is not activated merely by having the annotation on a class | Add `@EnableJms` or register listener containers manually |
| No default `jmsListenerContainerFactory` | Listener endpoints lack a container factory; registration can fail | Create the bean with the default name or specify `containerFactory` on the annotation |
| `OrderListener` not registered as a Spring bean | Annotations on unmanaged objects are never discovered | `@Bean`, `@ComponentScan`, or equivalent registration |
| Wrong queue/topic semantics | Producer/consumer exist, yet destinations mismatch or broker misroutes | Align `pubSubDomain`/destination resolver and policies |
| Wrong username/URL | Connection/auth/reconnect failures; producer/consumer cannot exchange messages | Fix networking, TLS, ACLs, and provider-specific properties |

**Note:** `@EnableJms` serves **listener annotation infrastructure only**. Spring JMS `JmsTemplate` can **send** without `@EnableJms` as long as you declare and inject valid `JmsTemplate`/`ConnectionFactory` beans. Do not treat "having `@EnableJms`" as sufficient validation for both sending and receiving.

## 6. Example B — Spring Boot: Same Business Logic, Less Boilerplate

Here Boot detects the Artemis starter/provider and combines `application.yaml` to create and register JMS beans in the `ApplicationContext`.

### 6.1. `build.gradle` for a Standalone Spring Boot App

Example uses Spring Boot 3.3.13 (an actual release on the 3.3 line). For new projects, pick a release line still under support per team policy rather than treating 3.3.13 as "latest":

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

**No need** to declare `spring-jms`, `jakarta.jms-api`, and `artemis-jakarta-client` separately here: the starter/BOM manages compatible dependency versions. Start with minimal dependencies and run `./gradlew dependencies --configuration runtimeClasspath` to verify what is actually resolved.

### 6.2. `application.yaml`: External Broker Configuration

File `src/main/resources/application.yaml`:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
  jms:
    pub-sub-domain: false
    cache:
      session-cache-size: 5
~~~

Supply the password via environment variable **`SPRING_ARTEMIS_PASSWORD`** at runtime (Spring Boot relaxed binding), or via an organization-approved secret store/config system. If the broker requires authentication and lacks valid credentials, connecting will fail; the YAML above does not supply a password by itself.

- `spring.artemis.mode=native`: connect to an **externally running broker** instead of expecting an embedded server.
- `spring.artemis.broker-url`, `user`, `password`: inputs for Artemis auto-configuration to build the client connection factory.
- `spring.jms.pub-sub-domain=false`: interprets destination names as **queues** by default. For topics, update the policy on both producer and listener or use dedicated templates/factories.
- `spring.jms.cache.session-cache-size`: configures session caching on Boot's `CachingConnectionFactory` for sending; it is **not** the number of consumers or allowed concurrent connections.
- No `@Bean ConnectionFactory` in this example: that is precisely the boilerplate Boot eliminates.

### 6.3. Complete Boot Application Java Code

File `src/main/java/example/jmsboot/BootJmsApp.java`:

~~~java
package example.jmsboot;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class BootJmsApp {
    public static void main(String[] args) {
        SpringApplication.run(BootJmsApp.class, args);
    }

    @Bean
    ApplicationRunner sendOne(JmsTemplate template) {
        return args -> {
            template.convertAndSend("orders.inbox", "order-42");
            System.out.println("Producer sent order-42");
        };
    }
}

@Component
class BootOrderListener {
    @JmsListener(destination = "orders.inbox")
    public void onMessage(String body) {
        System.out.println("Consumer received " + body);
    }
}
~~~

Run:

~~~bash
./gradlew bootRun
~~~

**Same conditions as Example A:** a real broker must be ready, the queue must exist or auto-create must be allowed, and credentials/permissions must be valid. Once connected, the listener can print the message, though log order between producer and consumer is non-deterministic. On every restart, `ApplicationRunner` **sends a new message on startup**; in production, events should be emitted from business operations rather than a startup runner.

**What Boot does for you:**

1. Creates the Artemis `ConnectionFactory` from dependencies and properties when auto-configuration conditions match.
2. By default wraps the native provider factory in Spring's `CachingConnectionFactory` for the `JmsTemplate` path; configured via `spring.jms.cache.*`.
3. Creates a `JmsTemplate` injectable into `sendOne`, backed by the proper `ConnectionFactory`.
4. Activates `@JmsListener` discovery infrastructure and creates the default listener factory/container when no custom bean is defined.
5. Attaches `MessageConverter`, `DestinationResolver`, and listener settings from context/properties when applicable.

**What Boot does not do for you:** it does not validate business schemas, guarantee exactly-once consumption, start an external broker, or provision network/TLS/ACLs/retention/DLQ. Default settings must still be tested against real failures and transaction tests.

## 7. Most Common Confusion: `@EnableJms` and Automatic `@JmsListener` Discovery

### Plain Spring Framework

~~~java
@Configuration
@EnableJms
class ListenerConfiguration {
    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

This **snippet** requires imports for `@Configuration`, `@Bean`, `@EnableJms`, `ConnectionFactory`, and `DefaultJmsListenerContainerFactory` as in Example A. `@EnableJms` imports JMS listener annotation infrastructure; when Spring finds beans with `@JmsListener`, it uses the default factory named `jmsListenerContainerFactory` unless the annotation specifies another factory.

### Spring Boot

Boot JMS auto-configuration normally imports the required listener infrastructure automatically, so Example B works **without `@EnableJms`**. Adding `@EnableJms` alone does not replace `ConnectionFactory`, and it should not be treated as a blanket fix for listener issues.

How to diagnose when a listener does not run:

- Is the listener bean in a package scanned by `@SpringBootApplication`, or registered via `@Bean`?
- Does `ConnectionFactory` exist and point to the right broker/destination?
- Is there a suitable `DefaultJmsListenerContainerFactory`? Does `@JmsListener(containerFactory="...")` match its name?
- Is the destination a queue or topic? Are there waiting messages, TTL/selectors, ACLs, or durable subscriptions?
- Is the listener container reconnecting or stopped due to connection/transaction/conversion errors?

**Classic mistake:** a class has `@JmsListener` but was instantiated manually with `new` outside the Spring container; Boot will never detect annotations on unmanaged instances.

## 8. Distinguishing ConnectionFactory, CachingConnectionFactory, and Pooling

### 8.1. Native ConnectionFactory

`jakarta.jms.ConnectionFactory` is the standard interface. Artemis's `ActiveMQConnectionFactory` is the provider implementation; it knows the broker URL, user, password, TLS/transport, failover, and how to open JMS `Connection`s. In Example A, the application declares this bean directly.

### 8.2. Spring `CachingConnectionFactory`

`org.springframework.jms.connection.CachingConnectionFactory` is Spring's wrapper around a native connection factory: it can hold a shared `Connection` and cache `Session`, `MessageProducer`, and `MessageConsumer` instances per configuration; its default session cache size is small and must be tuned for concurrency. It is not equivalent to a full **pool of physical connections** with limits, fairness, validation, and blocking semantics.

Important caveat: listener containers like `DefaultMessageListenerContainer` typically manage their own connection recovery and session/consumer lifecycles. Boot docs recommend **listener factories use the native `ConnectionFactory`**, whereas the caching wrapper fits many short-lived send calls via `JmsTemplate`. Boot unwraps the caching wrapper when configuring the default listener.

In plain Spring, the split can look like this:

~~~java
// Configuration snippet: nativeCf is an Artemis ConnectionFactory bean.
CachingConnectionFactory sendCache =
        new CachingConnectionFactory(nativeCf);
sendCache.setSessionCacheSize(5);

JmsTemplate sender = new JmsTemplate(sendCache);

DefaultJmsListenerContainerFactory listenerFactory =
        new DefaultJmsListenerContainerFactory();
listenerFactory.setConnectionFactory(nativeCf); // native for listener
listenerFactory.setSessionTransacted(true);
~~~

This is an **illustrative snippet**, not a standalone runnable program: if placed in Spring, register `sendCache` as a managed bean with proper lifecycle so it closes on shutdown. When both native and cached beans implement `ConnectionFactory`, use `@Qualifier` or `@Primary` explicitly to avoid ambiguous injection.

### 8.3. Native Pool

If high load requires **multiple physical connections** with capacity controls, consider a provider/adapter-supported pool. For example, with Boot 3.x and Artemis, adding `org.messaginghub:pooled-jms` enables:

~~~yaml
spring:
  artemis:
    pool:
      enabled: true
      max-connections: 20
~~~

This is an **alternative configuration option**; do not drop it into Example B expecting the caching wrapper to behave identically. Read broker/provider docs on session pooling, transaction boundaries, health checks, and connection lifetimes. Never use `spring.jms.cache.session-cache-size` to infer a pool's `max-connections`.

### 8.4. "Having a `ConnectionFactory` Bean" Does Not Mean "Connectivity Is Proven"

Instantiating a JMS client bean may only store endpoints/credentials without opening a socket right away. Never treat **Spring context started cleanly** as proof of successful broker login, queue authorization, or network message delivery. Run a real send/receive test and inspect the broker.

## 9. Transactions and Acknowledgement: Two Setup Styles Can Have Different Defaults

### 9.1. Plain Spring Framework Must Decide Explicitly

A `DefaultJmsListenerContainerFactory` created in plain Spring only gets the settings you configure. Without enabling transactions, the container may use `AUTO_ACKNOWLEDGE`, where depending on container type, ACK happens before or after the handler; with `DefaultMessageListenerContainer`, throwing an exception in the default mode does not guarantee redelivery. For important workloads, start with:

~~~java
factory.setSessionTransacted(true);
~~~

Then each receive/handler runs inside a **local JMS transaction**. If the handler succeeds, JMS commits; an eligible exception triggers rollback and potential broker redelivery per policy. Verify actual delays, retry limits, and DLQ behavior on the provider.

### 9.2. Spring Boot Configures Transactional Listeners by Default

Spring Boot 3.x documentation states **the default `JmsListenerContainerFactory` is transactional**:

- If a suitable `JtaTransactionManager` is present, Boot binds it to the listener container by default.
- Without JTA, Boot enables `sessionTransacted=true` on the default listener factory.

This does not mean any `@Transactional` annotation turns JMS + JDBC + HTTP into **one distributed transaction**. With a local DB transaction, Boot/Spring can synchronize JMS ack to run after the DB transaction completes, yet a **failure window** still exists between DB commit and JMS commit; consumers must tolerate replays.

**Comparison risk:** copying a `@JmsListener` method from Boot into plain Spring without copying/understanding the listener factory setup can silently change ack/rollback semantics even though handler code did not change at all.

### 9.3. Producer Transactions Are Also Separate

- `JmsTemplate.convertAndSend` normally sends over a non-transacted session outside a transaction context, unless the template or an active transaction manager/JMS session is configured accordingly.
- `JmsTemplate` can join a Spring-managed JMS transaction; `JmsTransactionManager` manages **one JMS resource**, not a DB alongside it.
- To publish events alongside DB transactions without "DB committed but JMS never sent," design a **transactional outbox**, bounded publisher retries, and idempotent consumers. Use XA/JTA only when genuinely required and supported by infrastructure.

**Test point:** intentionally throw an exception from the listener and observe queue depth/redelivery; simulate a crash between DB commit and JMS commit to see why duplicate detection remains necessary.

## 10. Auto-Configuration Is Conditional Rules, Not Magic

When Boot starts, auto-configuration classes evaluate **classpath, bean definitions, properties, and infrastructure state**. Depending on the provider, Boot looks for a compatible client, the JMS API, and the absence of already-defined beans it would otherwise create.

Suppose you run Example B:

1. Add `spring-boot-starter-artemis` → Spring Boot gets the Artemis driver and Spring JMS.
2. Add `spring.artemis.mode=native` and broker URL → Boot selects native client configuration.
3. No custom `ConnectionFactory` satisfies Artemis config conditions → Boot registers the provider factory and cache/pool wrapper.
4. No custom `JmsTemplate` or `JmsOperations` bean satisfies template conditions → Boot creates the template.
5. No custom default `JmsListenerContainerFactory` exists → Boot provides the factory used by `@JmsListener`.

These steps describe **conditional behavior**, not a guarantee that identical bean names/types appear in every version. If you declare **your own `ConnectionFactory` bean**, Boot's provider factory creation may back off; Boot's template/listener can still use your bean if autowiring is unambiguous. If you declare `JmsTemplate`, Boot generally will not overwrite it. When multiple `ConnectionFactory` beans or listener factories exist, use explicit `@Qualifier`/names.

### 10.1. You Can Customize Boot Incrementally Without Rewriting Everything

Scenario: needing a different message converter while letting Boot keep managing broker/client/template:

~~~java
@Bean
org.springframework.jms.support.converter.MessageConverter
messageConverter() {
    return new org.springframework.jms.support.converter.SimpleMessageConverter();
}
~~~

This snippet illustrates registration; `SimpleMessageConverter` is already the usual default, so returning it **adds no new behavior**. With an actual custom converter like JSON, define schema/type mapping, deserialization failure handling, and interoperability. Boot can attach a converter bean to auto-configured components depending on version conditions.

Scenario: customizing a listener factory while keeping Boot's default settings. On Boot 3.x, use `DefaultJmsListenerContainerFactoryConfigurer` to apply Boot's defaults, then customize:

~~~java
@Configuration
class CustomListenerConfig {

    @Bean
    DefaultJmsListenerContainerFactory criticalQueueFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        factory.setConcurrency("2-5");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

This snippet needs imports:
- `org.springframework.context.annotation.Bean` and `Configuration`.
- `jakarta.jms.ConnectionFactory`.
- `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer`.
- `org.springframework.boot.jms.ConnectionFactoryUnwrapper`.
- `org.springframework.jms.config.DefaultJmsListenerContainerFactory`.

Use `@JmsListener(destination = "critical.orders", containerFactory = "criticalQueueFactory")` on a listener bean. **A custom-named factory** does not replace Boot's default `jmsListenerContainerFactory` unless you explicitly specify it. `ConnectionFactoryUnwrapper.unwrapCaching` preserves Boot's practice of avoiding passing the caching wrapper directly to listeners. On other Boot versions, verify packages/APIs rather than copying blindly.

### 10.2. Reading the Condition Evaluation Report

When "the starter is there, yet the bean is missing," run the Boot app with debug enabled to inspect **positive/negative matches**:

~~~bash
./gradlew bootRun --args='--debug'
~~~

In the report, locate auto-configuration groups related to `Artemis`, `Jms`, and `JmsAnnotationDriven` along with `@ConditionalOnClass`, `@ConditionalOnBean`, and `@ConditionalOnMissingBean` conditions. Exact class names can vary across releases; the report's value is **why a condition matched or did not match**, not memorizing auto-config class names.

In production, never leave verbose debug logging enabled indefinitely. If Actuator is enabled with proper access controls, conditions/beans endpoints can help inspect wiring, though never expose sensitive endpoints publicly.

## 11. Properties vs. Code Configuration: Choose by Scope of Change

| Need | Prefer in Boot | When to declare beans yourself |
| --- | --- | --- |
| Changing Artemis broker URL/user/password | `spring.artemis.*` or equivalent env variables | Provider topology or security config exceeds property scope |
| Choosing default queue vs. topic | `spring.jms.pub-sub-domain` | App uses both queues and topics with distinct policies |
| Tuning session cache | `spring.jms.cache.session-cache-size` | Need fine-grained pool/wrapper control per profile |
| Tuning listener concurrency / ack / transactions | `spring.jms.listener.*` where supported by version | Need separate factories and policies per queue class |
| JSON schema/message converter | Converter bean + appropriate config | Need complex converter with custom mapping/versioning |
| Multiple brokers or multiple credentials | App-owned multi-factory config | Usually requires `@Qualifier`, multiple templates, multiple listener factories |
| Provider-specific TLS/client failover | Check Boot properties + transport URI support | Need custom client library or builder/provider bean |
| XA/JTA and resource coordination | Explicitly chosen JTA infrastructure | Need XA `ConnectionFactory`/transaction manager config and integration proof |

**Configuration principle:** Boot apps should start with properties plus targeted beans. Redefining the entire `ConnectionFactory` or `JmsTemplate` just to change an endpoint often drops caching, converters, retry/error handling, or other auto-config conveniences unintentionally.

## 12. ConnectionFactory in Application Servers, JNDI, and Multiple Providers

Not every app constructs an Artemis client with `new ActiveMQConnectionFactory(...)`. Inside a **Jakarta EE application server**, `ConnectionFactory` may be container-managed and looked up via **JNDI**:

- In plain Spring, use `JndiObjectFactoryBean` or a JNDI lookup, then inject `jakarta.jms.ConnectionFactory`.
- In Spring Boot 3.x, `spring.jms.jndi-name` can look up the JMS `ConnectionFactory` instead of Boot building a provider CF from a URL (when environment conditions match).

**Avoid conflicting setups:** simultaneously configuring a JNDI factory, an Artemis native factory, and a custom provider factory without clarifying which bean feeds templates and listeners. With XA/JTA, a raw native client and an app-server-managed connection can have different transaction semantics. Always verify the **actual bean graph**.

### When Multiple Brokers Appear Together

For example, connecting separately to "payments" and "notifications" brokers:

~~~text
paymentsConnectionFactory
    ├─ paymentsJmsTemplate
    └─ paymentsListenerFactory

notificationsConnectionFactory
    ├─ notificationsJmsTemplate
    └─ notificationsListenerFactory
~~~

Here **Spring Boot auto-config cannot guess** which queue belongs to which broker. Use explicit bean names, `@Qualifier`, clear destination config, and `containerFactory` on `@JmsListener`; you can keep auto-config for one default factory, yet you should control all routing deliberately.

Do not share classic JMS API `Session` or `MessageProducer` objects across threads; use `JmsTemplate` or resources whose lifetimes are managed properly by the framework.

## 13. Destinations, Pub-Sub, Converters, and Listener Routing

### 13.1. Default Is Queue, Not Topic

In Example B, `spring.jms.pub-sub-domain=false` (default) resolves `orders.inbox` as a **queue** in the template and default listener factory. For topics, enable `spring.jms.pub-sub-domain=true` when **the entire default flow** genuinely uses topics. If an application uses both, design **two templates/listener factories** with corresponding `setPubSubDomain(...)`; flipping a global property can break existing queue paths.

A destination name does not prove the broker provisioned it; some providers auto-create resources while others require prior provisioning and permissions. Durable topic subscriptions also require client/subscription identity, retention, and dedicated policies.

### 13.2. `MessageConverter` Affects Data, Not Networking

`JmsTemplate.convertAndSend(...)` uses a converter to build a JMS `Message` from a Java object; listeners convert payloads back into `String`/objects. When sending Strings, `SimpleMessageConverter` typically creates a `TextMessage`. When sending POJOs, **do not assume automatic JSON conversion** without a JSON converter and clear type mapping.

In plain Spring, you create and attach `MessageConverter` to templates and listener factories as needed. In Boot, registering a converter bean lets auto-configured templates/default listeners pick it up, whereas custom factories/templates you create manually may need the converter wired explicitly.

### 13.3. Listener Containers Have Their Own Lifecycles

A `@JmsListener` operates through a container managing consumers and connections; it can start on context refresh, retry on broker disconnect, and stop on shutdown. A publisher sending successfully at startup does not mean consumers are ready at that same instant. To verify readiness, check listener container status, broker connections, queue depth, and actual message handling.

## 14. Experimental Verification Matrix: Proving Equivalence and Differences

Run these sequentially with **two standalone apps** from Examples A/B against the same broker/queue:

| Test | Plain Spring | Spring Boot | What to observe |
| --- | --- | --- | --- |
| Stop broker before startup | `ConnectionFactory` bean may instantiate; listener logs reconnect; send fails | Context may also start, yet send/listener fail depending on connection timing | Bean existing **differs** from broker reachable |
| Broker running, valid queue | Sends and listener receives | Sends and listener receives | Underlying JMS traffic is identical |
| Remove `ConnectionFactory` config in A | Missing bean → wiring error | B can still create CF from starter/properties | Difference in bean ownership |
| Remove `@EnableJms` in A | Annotated listener is not activated | B needs no explicit `@EnableJms` in standard setup | Difference in listener infrastructure bootstrap |
| Remove listener factory in A | Infrastructure lacks default factory unless registered otherwise | B auto-configures default factory when eligible | Difference in auto-registration |
| Throw exception in handler | A's local JMS transaction rolls back | Boot's default transactional factory rolls back (unless overridden) | Inspect redelivery/DLQ per broker |
| Change broker credentials | Edit A's env/client bean | Edit B's `SPRING_ARTEMIS_*`/properties | Two ways of injecting config |
| Add custom `JmsTemplate` bean in B | Boot auto-config not applicable | Boot may back off default template | Conditional auto-configuration |

**Run safely:** use a test queue, a test broker, and messages with clear `eventId`s; never test failures with production data. Record classpath, config, stack traces, listener receive timestamps, and remaining broker messages for each test.

## 15. Concrete Debugging from Symptom to Root Cause

| Symptom | Likely root cause | Verify without guessing |
| --- | --- | --- |
| `No qualifying bean of type 'jakarta.jms.ConnectionFactory'` | Missing provider bean in plain Spring; or Boot auto-config did not match due to missing starter/bean conflict | Check dependency graph, bean definitions, and condition report |
| `No qualifying bean of type 'JmsTemplate'` | Plain Spring lacks template bean; Boot template condition did not match | Check `@Bean JmsTemplate` or Boot report |
| `No bean named 'jmsListenerContainerFactory'` | Annotation infrastructure has no matching default container factory | Check bean name, `@EnableJms`, and `containerFactory` |
| Boot starts, yet listener processes nothing | Missing component scan, wrong destination, broker unreachable, ACL, selector, topic/queue mismatch | Read container + broker logs; confirm destination/consumer count |
| `ClassNotFoundException: javax.jms...` or `jakarta.jms...` | Mixing old/new JMS client APIs | Check `runtimeClasspath`; pick Artemis Jakarta client for Spring 6 |
| `UnknownHostException`, connect timeout, refused | Wrong URL/DNS/firewall/acceptor or broker not running | Check actual endpoint, broker listeners, and TCP/TLS |
| `JMSSecurityException` | Wrong user/password/roles/ACL | Check secret binding and broker auth logs; never print credentials |
| Sent OK, yet nothing received | Wrong queue/topic, consumer unstarted, another listener grabbed it, TTL expired, broker routed elsewhere | Check queue depth, subscriptions, routing type, and `JMSDestination` |
| Message processed twice on retry | Local JMS transaction retry/redelivery or duplicate publisher send | Stable event ID, dedupe unique constraint, transaction + DLQ |
| Boot loses settings after adding a custom bean | New bean caused auto-config back-off, or `@Primary`/`@Qualifier` shifted wiring | Condition report, bean graph, and effective properties |
| Listener spawns more threads than expected | `concurrency`/provider dispatch semantics | Check actual factory in use and live consumer count on broker |
| Changing `spring.jms.cache.*` doesn't change pool | Session cache differs from physical connection pool | Inspect actual wrapper/pool class and metrics |

**Start with concrete technical questions:** "Which `ConnectionFactory` bean is in the container? What is its runtime class? Which factory bean was picked for the listener? Is the broker actually connected?" Answer each with runtime evidence before editing config.

## 16. Common Boot Override Patterns

### 16.1. Declaring Your Own `ConnectionFactory` in a Boot App

~~~java
@Configuration
class ExternalJmsConfiguration {
    @Bean(destroyMethod = "close")
    ActiveMQConnectionFactory connectionFactory() {
        return new ActiveMQConnectionFactory(
                "tcp://localhost:61616", "demo", readSecret());
    }

    private String readSecret() {
        String password = System.getenv("JMS_PASSWORD");
        if (password == null || password.isBlank()) {
            throw new IllegalStateException("JMS_PASSWORD required");
        }
        return password;
    }
}
~~~

This snippet needs imports for `@Configuration`, `@Bean`, and `ActiveMQConnectionFactory` as in Example A. Placed in a Boot app, **your custom provider `ConnectionFactory` bean** can stop Artemis auto-config from creating its factory as before. Depending on definitions/names, Boot may still create `JmsTemplate` and the listener factory **using your bean**. Do not expect `spring.artemis.broker-url` to override the hardcoded constructor: code and properties now hold **two configuration sources**, with your custom bean dictating the real client.

Usually, if you only want to change host/user, the better fix is to **remove the custom `ConnectionFactory`** and use `spring.artemis.*`. Keep a custom bean only when you need multiple brokers, custom TLS/failover/provider options, JNDI, or policies auto-config cannot express.

### 16.2. Declaring Your Own `JmsTemplate`

~~~java
@Bean
JmsTemplate specialTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setPubSubDomain(true);
    return template;
}
~~~

If this is the only `JmsTemplate` bean, Boot may skip creating its default template. The app then uses your template; `spring.jms.template.*` properties are **no longer guaranteed** to apply to it. If you want a default queue template plus a separate topic template, name beans clearly, use `@Qualifier` at injection points, and verify conditional auto-config/`@Primary`.

### 16.3. Declaring Your Own Listener Factory

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-4");
    return factory;
}
~~~

With **the exact default name**, Boot may back off creating its default factory. Listeners then use your settings; if you forget `sessionTransacted` or `MessageConverter`, semantics can differ from Boot's defaults. With a **custom-named** factory, use `@JmsListener(containerFactory="...")` to select it explicitly. To inherit Boot's behavior, use `DefaultJmsListenerContainerFactoryConfigurer` instead of manually setting every property and risking omissions.

## 17. Migration Strategy: Plain Spring ↔ Spring Boot

### 17.1. From Plain Spring to Boot

1. **Snapshot the working config:** provider/version, URL/TLS, security, destination resolvers, pub-sub, converters, connection caching/pooling, transactions, concurrency, retries, and DLQ.
2. **Add the provider's Boot starter** and adopt dependency management. Remove duplicate Spring/provider version pins only after inspecting the dependency graph.
3. **Move simple properties** to `spring.artemis.*`, `spring.jms.*`, and environment/secret managers. Never store secrets in source control.
4. **Remove redundant beans replaceable by auto-config**: typically `ConnectionFactory`, `JmsTemplate`, and default listener factory; keep custom beans that add real value.
5. **Inspect condition report + bean graph** to see what Boot creates and where it backs off; never rely solely on app startup succeeding.
6. **Compare transaction defaults:** if the old config used `AUTO_ACK` while Boot defaults to transacted, listener error behavior will change—that is a business-level change requiring testing.
7. **Run integration tests against a real broker:** send/receive, queue/topic, retry/DLQ, broker restart, idempotency, redelivery, and shutdown.

### 17.2. From Boot to Plain Spring

1. List all beans **Boot auto-configured** at runtime: `ConnectionFactory` (native/wrapper), `JmsTemplate`, `JmsListenerContainerFactory`, converters/resolvers.
2. **Explicitly recreate** the required beans in `@Configuration` and `@EnableJms`; record factory names/qualifiers.
3. Translate `spring.artemis.*` and `spring.jms.*` into a property-binding mechanism suited to plain Spring; they do nothing on their own without Boot's binder/configurer.
4. Assemble the right classpath (Spring 6/Jakarta provider) and pin verified dependency versions.
5. Compare **ack/transactions, caching/pooling, listener recovery, and concurrency** before considering migration done. Use the same test broker and failure drills as Boot.

**Config source warning:** setting `spring.artemis.broker-url` in a **plain Spring** app does not automatically create an Artemis `ConnectionFactory` just because the property name "looks Spring-standard." You must have code/binder reading that property and constructing the bean. Conversely, a manual `@Bean ActiveMQConnectionFactory` inside Boot may ignore `spring.artemis.*` unless you pass those values into its constructor.

## 18. Exercises to Verify Deep Understanding

**Exercise 1 — Draw the bean graph:** For Example A, draw `ConnectionFactory → JmsTemplate` and `ConnectionFactory → jmsListenerContainerFactory → @JmsListener`. List each `@Bean` to declare and why.

**Exercise 2 — Remove one bean at a time:** In plain Spring, remove `JmsTemplate`, `ConnectionFactory`, and `jmsListenerContainerFactory` one by one in a test environment. Read each exception and identify the missing bean.

**Exercise 3 — Prove Boot auto-config:** Run Example B with `spring-boot-starter-artemis` and print the condition report using `--debug`. Inspect runtime bean types, proving Boot configured both template and listener factory.

**Exercise 4 — Test backing off:** Add a custom `JmsTemplate` to B and observe bean types and whether `spring.jms.template.*` still affects the custom template. Do not guess; use the condition report and actual send behavior.

**Exercise 5 — Compare queue/topic:** Create dedicated test queues and topics; test default `pubSubDomain` and custom factories. Observe broker routing/subscriptions instead of just reading destination names.

**Exercise 6 — Intentional listener failure:** Throw an exception inside `@JmsListener` to observe redelivery under a local JMS transaction. Compare with a plain Spring factory without `sessionTransacted`; explain why Boot's default can differ.

**Exercise 7 — Broker restart:** When the broker is unavailable, watch startup, reconnect logs, producer send exceptions, listener recovery, and time to resume receiving. Prove **instantiating beans** does not mean **the broker is connected**.

**Exercise 8 — Distinguish cache/pool:** Send many concurrent messages in a test; observe session cache, consumer count, and physical connection count. Change `session-cache-size` and compare with a pool using `max-connections` to see what each parameter measures.

**Exercise 9 — Multi-broker:** Design two `ConnectionFactory` beans and two listener factories with explicit qualifiers; trigger injection ambiguity first, then resolve it with bean names. Never use an implicit `@Primary` as a business routing mechanism.

**Exercise 10 — Migration testing:** Run the same 5 checks (send, listener receive, exception rollback, broker restart, malformed payload) in both plain Spring and Boot apps. Record app/broker configs and actual results; conclude which differences came from auto-configuration and which came from different settings you chose.

## 19. Connection Setup Completion Checklist

- [ ] Identified the right **JMS provider** and Jakarta dependencies compatible with Spring 6+/Boot 3+.
- [ ] Know whether the broker runs externally or embedded; verified URL, DNS, port, TLS, credentials, and ACLs.
- [ ] Can point to **the active `ConnectionFactory` bean**, what created it, and whether it is native or wrapped.
- [ ] Can explain why plain Spring needs `@Bean`/`@EnableJms` config while Boot provides them conditionally.
- [ ] Know when Boot auto-config **backs off** and why custom beans may ignore `spring.jms.*`.
- [ ] Have `JmsTemplate` for publishers and a properly named listener factory/container for `@JmsListener`.
- [ ] Aligned queue/topic mode, resolvers, and converters with broker destinations.
- [ ] Verified default listener transaction/ack on **the real runtime**; tested exceptions/redelivery and understand limits with separate DB transactions.
- [ ] Have appropriate caching/pooling, distinguishing session cache size from pool max connections.
- [ ] Have logs/metrics/health covering real connections, queue depth, active listeners, auth errors, and retries/DLQ.
- [ ] Tested at least one send/receive round-trip and one broker outage scenario rather than relying on startup success.

**Target capability:** Given the requirement "send and receive messages from a queue," you can deliberately **assemble all configuration in plain Spring Framework**, or **explain precisely which beans Spring Boot auto-configures and when it skips creating them**, while verifying connectivity, listeners, and transactions on a real system.

## Official References for Verification

1. [Spring Framework Reference — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@EnableJms`, default `jmsListenerContainerFactory`, `@JmsListener`.
2. [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate`, `CachingConnectionFactory`, destination converters, transactions.
3. [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener container lifecycle, `sessionTransacted`, reliability.
4. [Spring Boot 3.4 Reference — JMS](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html): Artemis auto-configuration mechanics, connection caching/pooling, JNDI, template/listener factory, and transactional defaults (cross-check against Boot 3.3 if running examples).
5. [Spring Boot 3.3 Reference — JMS](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html): APIs/properties for the 3.3 branch.
6. [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): simple Boot send/receive app without manually creating `ConnectionFactory` and `JmsTemplate`.
7. [Apache ActiveMQ Artemis — Using JMS](https://artemis.apache.org/components/artemis/documentation/latest/using-jms): provider, transports, and destination behavior.
8. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS API contract, sessions, acknowledgements, and transactions.

**Scope of applicability:** Provider-specific settings (authentication/TLS, address-routing, auto-create, redelivery, DLQ, HA) require reading **documentation for your exact provider and broker version**, never inferring them solely from Spring auto-configuration.