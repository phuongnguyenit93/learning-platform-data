# Choosing a JMS Provider and Compatible Client Library in Spring

## 1. Why Must You Choose Both the Provider and Client Correctly?

**JMS (Jakarta Messaging, formerly Java Message Service)** is a **standard API** for Java programs to send and receive messages asynchronously. The API defines concepts such as `ConnectionFactory`, `Connection`, `Session`, `MessageProducer`, `MessageConsumer`, `Queue`, and `Topic`; however, the API itself **is not a message broker** and **does not standardize the wire protocol between client and broker**.

A working JMS system requires at least three parts:

~~~text
Spring application                      Messaging infrastructure
┌─────────────────────────────────┐
│ Service / @JmsListener          │
│      ↓                          │
│ JmsTemplate / listener container│
│      ↓                          │
│ jakarta.jms.ConnectionFactory   │  ← standard API
│      ↑                          │
│ Provider's JMS client           │  ← implements API, TLS, reconnect,
└────────────┬────────────────────┘     codec, protocol, authentication
             │ compatible network protocol
             ▼
        JMS broker / provider
        (Artemis / ActiveMQ Classic / IBM MQ / ...)
~~~

Spring JMS can use the same programming model across multiple providers because it depends on `jakarta.jms.ConnectionFactory`. However, the client library must be compatible on **two sides**: (1) the Java interfaces used by your Spring version and (2) the broker, protocol, server version, security, and JMS features actually required.

**Lesson objective:** know what questions to ask when choosing a broker, find the right client library (without confusing the API JAR with the provider JAR), understand the `javax.jms`/`jakarta.jms` boundary, configure it with Spring Boot, and run an end-to-end smoke test before deciding to use it in production.

## 2. Distinguishing Five Layers of Compatibility

| Layer | Question to answer | Example failure if ignored |
|---|---|---|
| **Java API** | Does the client implement `jakarta.jms` or `javax.jms`? Does the API version match Spring Framework? | `NoClassDefFoundError`, `ClassCastException`, unable to assign `ConnectionFactory`. |
| **Client implementation** | Which specific JAR creates `ConnectionFactory` and implements the required JMS methods? | Adding only `jakarta.jms-api`, leaving no actual provider. |
| **Protocol / transport** | Does the broker accept Core, OpenWire, AMQP 1.0, or a proprietary protocol? Does the client speak the right protocol on the right port/acceptor? | TCP connection opens, but protocol handshake fails. |
| **Features / semantics** | Do you need Queue, Topic, durable/shared subscriptions, selectors, delayed delivery, acknowledgement, transactions/XA, DLQ, failover? | Code compiles, but an operation throws `UnsupportedOperationException` or behaves differently than expected. |
| **Operations and security** | Do TLS, SASL, credentials, ACLs, high availability, quotas, observability, patches, licensing/support, and latency fit? | Works locally, but fails on certificates, authorization, or failover upon deployment. |

Satisfying one layer **does not imply** satisfying all layers. "Both are JMS" does not mean "broker A's client can always connect directly to broker B."

### The JMS API Is Not a Wire Protocol

For example, Apache ActiveMQ Artemis supports protocols such as **Core, AMQP 1.0, OpenWire, MQTT, and STOMP**. Those capabilities serve different kinds of clients; the Java application's JMS API is translated by the client/provider into a specific protocol. A client supporting AMQP 1.0 can communicate with an Artemis broker if the acceptor and features are compatible, but you must test specific JMS semantics. Do not assume an older `javax.jms` client can plug into Spring Framework 6 just because they share a network protocol.

## 3. Questions About Requirements Before Comparing Products

First, describe the workload with measurable information:

1. **Messaging pattern:** Queue distributing work among consumers, or Topic broadcasting to subscriptions? Do you need durable subscriptions, shared subscriptions, selectors, message priority, or message TTL?
2. **Delivery guarantees:** Are at-least-once delivery and deduplication acceptable? When a consumer is offline, how long do messages stay? Where will retries, poison messages, and dead-letter queues be handled?
3. **Load:** Messages per second, average and maximum size, number of producers/consumers, number of connections/sessions, peak load, allowable backlog, and acceptable latency.
4. **Transactions:** JMS local transactions only, combining with a DB via outbox/inbox, or genuinely needing XA/JTA? Do not assume every provider implements full XA.
5. **Existing systems:** Which brokers does the organization already run, what are the operational standards, and are there interoperability requirements between Java and .NET/Node/Python or legacy systems?
6. **Infrastructure:** On-premises, containers/Kubernetes, or managed service; HA, clustering, replication, TLS/mTLS, identity, monitoring, backups, retention policies, and commercial support.
7. **Technical compatibility:** JDK, Spring Framework/Spring Boot version, `jakarta.jms`/`javax.jms`, provider client and server versions.

A statement like "we want to send events to multiple services" is not enough to choose a broker. You need to know whether an offline subscriber must receive missed messages, whether load is shared within the same subscription, and what latency/retention requirements exist.

## 4. Comparing Common Options

| Option | When to consider | Java client / Spring integration | What must be verified |
|---|---|---|---|
| **Apache ActiveMQ Artemis** | New JMS project, self-operated broker, needing Queue/Topic and multi-protocol connectivity. | Spring Boot: `spring-boot-starter-artemis`; Jakarta client: `artemis-jakarta-client`. | Broker version, acceptor/protocol, anycast/multicast routing, persistence, HA, TLS, and subscriptions. |
| **Apache ActiveMQ Classic** | Existing ActiveMQ Classic/OpenWire system; wanting to keep the broker and upgrade clients incrementally. | Boot: `spring-boot-starter-activemq`; client branches `5.18.x`/`6.x` have different `javax`/`jakarta` boundaries. | Limitations in some JMS 2.0/Jakarta 3.1 APIs, shared subscriptions, 5-to-6 migration, embedded vs remote. |
| **IBM MQ** | Enterprise environment already running queue managers, needing integration, support, and IBM-standard security/operations features. | Corresponding Jakarta Messaging client and `com.ibm.mq:mq-jms-spring-boot-starter` matching the Boot version. | Queue manager/channel, CCSID, TLS, authority, CCDT, client version, licensing, and connection/failover rules. |
| **AMQP 1.0-capable broker with Qpid JMS** | Wanting a `jakarta.jms` application to connect to a compatible AMQP 1.0 endpoint. | `org.apache.qpid:qpid-jms-client` `2.x` line (Jakarta 3.1). | AMQP mapping to JMS destinations/headers/selectors, durable/shared semantics, SASL/TLS/failover. Qpid JMS is a **client**, not a broker itself. |
| **Other JMS providers** | Existing enterprise/managed messaging platform with a vendor-supported Jakarta library. | Vendor JAR/starter or a `@Bean ConnectionFactory` depending on the product. | Spring/JDK/Jakarta certification, protocol, XA documentation, security, support, and license limits. |

**RabbitMQ with `spring-boot-starter-amqp`** uses Spring AMQP and the RabbitMQ Java client, and **is not automatically a JMS provider**. Likewise, Kafka with Spring Kafka does not become a JMS broker simply because both address messaging. If you plan to use those technologies, prefer their native ecosystem integration APIs; only introduce a JMS layer when there is an official JMS adapter and its features have been tested.

### An Option Can Be Right Because of Existing Infrastructure

If an organization already runs IBM MQ with established operational standards and certificates, choosing IBM MQ and a compatible Jakarta client usually makes more sense than switching brokers just because a Spring example uses Artemis. Conversely, when you need an easy-to-stand-up JMS lab for Java/Spring, Artemis is a convenient hands-on choice. Base the decision on full lifecycle cost and **tested** features, not just product names.

## 5. The Most Important Compatibility Rule: javax.jms or jakarta.jms?

Minimal history:

| Application/API group | Package in Java code | Library group to look for |
|---|---|---|
| Java EE / JMS 1.1, JMS 2.0; most of Spring Framework 5 and Spring Boot 2 | `javax.jms.*` | A client implementing `javax.jms` matching the broker. |
| Jakarta Messaging 3.x; Spring Framework 6 and Spring Boot 3 | `jakarta.jms.*` | A client implementing `jakarta.jms` matching the broker. |
| Spring Framework 7 / Spring Boot 4 | `jakarta.jms.*` | Continue using a Jakarta client, but check Spring/JDK version requirements and Boot migration notes. |

Spring Framework 6 requires Java 17+ and uses the Jakarta namespace; **changing only your application imports from `javax.jms` to `jakarta.jms` is not enough**. The client implementation must also implement the interfaces in the right namespace. These classes:

~~~java
javax.jms.ConnectionFactory
jakarta.jms.ConnectionFactory
~~~

are **two different binary types** to the JVM. Do not try to cast a provider factory implementing `javax.jms.ConnectionFactory` to `jakarta.jms.ConnectionFactory`. Communication between old and new applications over a **shared broker/protocol** may still be possible; differing packages inside a single process is a separate matter from interacting over the network.

### Having Only the API JAR Cannot Send or Receive

~~~groovy
dependencies {
    // Interface/specification only, no broker implementation:
    compileOnly 'jakarta.jms:jakarta.jms-api:3.1.0'
}
~~~

This Gradle snippet illustrates an **insufficient dependency**; with only the API, Spring cannot automatically create a usable provider `ConnectionFactory`. In a Boot application, use a supported starter or pick a specific client JAR and configure the factory yourself; the BOM manages compatible versions. Do not add a pile of different clients "just in case": they easily cause transitive dependency conflicts and make auto-configuration unpredictable.

## 6. Choosing the Right Client Artifact by Provider

### 6.1. Apache ActiveMQ Artemis

For Spring Framework 6 / Boot 3 applications, prefer:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

The starter integrates Spring and the appropriate Jakarta client according to Boot's BOM. If using plain Spring without the starter, choose `org.apache.activemq:artemis-jakarta-client` (Jakarta Messaging 3.x) alongside `spring-jms` and declare a `ConnectionFactory`.

**Watch the artifact names carefully:**
- `artemis-jms-client` is the client line using the older `javax.jms` namespace, targeting JMS 2.0.
- `artemis-jakarta-client` is the `jakarta.jms` client line.
- `artemis-jakarta-server` is the embedded broker component when you want to run **embedded Artemis** in examples/labs, **not the client library needed for an application that only connects to an external broker**.

Keep Artemis modules aligned with the versions managed by the Boot BOM whenever possible. Do not force a newer client onto an older set of Artemis modules without running dependency resolution and compatibility tests.

### 6.2. Apache ActiveMQ Classic: Differences Between 5.18.x and 6.x

This is an easy place to get confused because the artifact keeps **the same name** `activemq-client` while the namespace changes across major versions:

| ActiveMQ Classic branch | Client artifact | API package | Notes |
|---|---|---|---|
| Regular `5.18.x` | `org.apache.activemq:activemq-client` | `javax.jms` | Suitable for legacy JMS code. |
| `5.18.1+` Jakarta transition | `org.apache.activemq:activemq-client-jakarta` | `jakarta.jms` | Client-only, for connecting to a remote broker; do not load the older `javax` client/broker in the same JVM for embedded/VM transport. |
| `6.x` | `org.apache.activemq:activemq-client` | `jakarta.jms` | The `activemq-client-jakarta` artifact is no longer needed. |

According to ActiveMQ Classic documentation, **some JMS 2.0/Jakarta 3.1 APIs are not yet fully supported** depending on the version, such as shared topic consumers or delayed/async send. A program that only uses `Queue`, `send`, and `receive` might run fine while a project requiring `createSharedDurableConsumer` fails. You must check the implementation progress table/release notes for the exact version and test the APIs you will use; do not rely solely on the API version declared in the POM.

Spring Boot 3 provides `spring-boot-starter-activemq`; choose the accompanying dependencies carefully and avoid pulling a `javax.jms` client back into a Jakarta context. With a Classic 5.x broker and the transitional Jakarta client, prefer **remote** connections per vendor docs rather than trying to embed a `javax` broker in the same Boot 3 JVM.

### 6.3. IBM MQ

IBM MQ has separate legacy JMS and Jakarta Messaging libraries. IBM MQ supports the Jakarta Messaging client starting from **9.3.0**; these libraries use `jakarta.jms` and can interoperate via the queue manager with older JMS clients, though you should not mix both client lines in **the same application**.

For Spring Boot, the starter provided by IBM is:

~~~groovy
dependencies {
    // Choose an IBM starter version compatible with your Spring Boot major/minor version
    // (do not copy a version from an old tutorial).
    implementation 'com.ibm.mq:mq-jms-spring-boot-starter:<compatible-version>'
}
~~~

The snippet above is a **dependency selection notation**, not a Gradle block that resolves as-is: replace `<compatible-version>` with a version IBM confirms is compatible. When actually configuring it, verify the queue manager, channel, hostname/port, TLS truststore, and access permissions. For Spring Boot 3, use the Jakarta starter/client line; do not mistakenly drop in `com.ibm.mq.allclient` from Spring Boot 2 examples.

### 6.4. AMQP 1.0 with Apache Qpid JMS

Qpid JMS **2.x** is a `jakarta.jms` client over the **AMQP 1.0** protocol, usable with brokers that expose a compatible AMQP endpoint; Qpid JMS **1.x** is the `javax.jms` line:

~~~groovy
dependencies {
    implementation 'org.springframework:spring-jms'
    implementation 'org.apache.qpid:qpid-jms-client:2.11.0'
}
~~~

This is a dependency fragment for a Jakarta application whose Spring version is already managed separately. You still must configure Qpid's `jakarta.jms.ConnectionFactory` bean and the AMQP endpoint; there is no Spring Boot Artemis/Classic auto-configuration for Qpid just because `spring-jms` is present. A broker vendor may speak AMQP 1.0 without implementing every JMS characteristic the way Qpid expects; **test selectors, message headers, durable subscriptions, transactions, and security** before committing to it.

## 7. Spring Boot and Dependency Management

When a compatible starter exists, let Spring Boot's BOM manage the dependencies it declares. Here is a **standalone lab** Gradle configuration with Java 17+ and Spring Boot 3.5.16 (representing the Spring Framework 6 line):

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-provider-compat'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'

    // Only needed to run an embedded Artemis broker for the lab.
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

Version `3.5.16` is chosen as a reproducible reference point for Spring Framework 6, **not as advice to pin a fixed version in production**. Choose a Spring Boot/JDK line that remains supported for your application lifecycle, use a compatible Gradle version (Boot 3.5 supports Gradle 8.x from 8.4+), and update for security advisories. Boot 4 lines may change starter/auto-configuration rules; check the corresponding documentation when doing a major upgrade.

**Do not use `spring-boot-starter-artemis` and `spring-boot-starter-activemq` simultaneously** as a way to "include both and pick at runtime." If you need two providers in one application, declare two named `ConnectionFactory` beans, explicitly wire the corresponding `JmsTemplate` and listener container, handle transactions separately, and review how to exclude auto-configuration.

### Inspecting the Gradle Dependency Tree

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency jakarta.jms-api
./gradlew dependencyInsight --configuration runtimeClasspath --dependency artemis-jakarta-client
~~~

On Windows PowerShell, replace `./gradlew` with `.\gradlew.bat` if the project has a Wrapper. When inspecting, verify you see the expected provider client, aligned Jakarta API and Spring versions; investigate any `javax.jms-api` or presence of both Artemis and Classic clients on the classpath. **Having transitive `javax.jms` does not automatically prove a failure**, but the runtime must never deliver the wrong kind of `ConnectionFactory` or expose the old API to Spring 6.

If you need to know which implementation libraries are actually present, examine the dependency graph and inspect the live implementation bean at runtime, not just the compile classpath.

## 8. Runnable Demo: Checking Embedded Artemis via a Round-Trip

This demo clarifies the final criterion: not just "dependencies resolved," but actually being able to **send and receive a real `TextMessage`** with the provider. It uses Spring Boot 3.5.16, Java 17, and Gradle as in section 7. No Docker or external broker is required because an embedded Artemis server is included.

Structure:

~~~text
jms-provider-compat/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jms/ProviderSmoke.java
    └── resources/application.yml
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: compat.check
      persistent: false
~~~

`src/main/java/example/jms/ProviderSmoke.java`:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class ProviderSmoke {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ProviderSmoke.class, args)) {

            // Ensure Spring injected a factory implementing jakarta.jms.
            ConnectionFactory factory =
                    context.getBean(ConnectionFactory.class);
            System.out.println("ConnectionFactory="
                    + factory.getClass().getName());

            JmsTemplate template = context.getBean(JmsTemplate.class);
            template.setReceiveTimeout(3_000);

            // No competing listener, so read back from the same queue.
            template.convertAndSend("compat.check", "ping");
            Object received = template.receiveAndConvert("compat.check");

            if (!"ping".equals(received)) {
                throw new IllegalStateException(
                        "Unexpected JMS payload: " + received);
            }

            System.out.println("ROUND_TRIP_OK=ping");
        }
    }
}
~~~

Run from the directory containing `build.gradle`:

~~~bash
./gradlew bootRun
~~~

If using Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

After the Spring Boot and Artemis log lines, if the run succeeds, the following line will appear:

~~~text
ROUND_TRIP_OK=ping
~~~

The `ConnectionFactory=...` line depends on the concrete class and any wrapper/cache, so **do not hardcode the class name in expected output**. This smoke test proves that the starter, provider client, embedded broker, Queue, `String` ↔ `TextMessage` conversion, and send/receive work **within a single process**. It does not yet prove network connectivity, TLS, failover, XA, or durability across broker restarts. `persistent: false` is only suitable for labs, not as a default guaranteeing storage in production.

### Switching to an External Artemis Broker

When running a separate broker, **remove the embedded server dependency** and change the application configuration as follows (hostname/port must be the broker's real endpoint):

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
~~~

Supply username/password via environment variables or a secret manager per deployment guidelines; for example, do not store passwords in Git. Create Queue `compat.check` on the broker or allow auto-creation according to broker policy. Re-run `./gradlew bootRun` and verify `ROUND_TRIP_OK=ping`; only then have you verified the **network protocol** between client and broker. If the broker uses TLS, you must configure the connector, truststore/certificate, and URL per the provider's specification, not just replace `tcp://` with an invented prefix.

### If Using ActiveMQ Classic

A **different** project can replace the Artemis starter with:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-activemq'
}
~~~

and declare:

~~~yaml
spring:
  activemq:
    broker-url: tcp://localhost:61616
~~~

This is a **remote connection** pattern; the application must have a compatible Classic broker and matching Queue. Do not keep `artemis-jakarta-server` in a Classic project or use both starters together. The Gradle/Java demo code only needs the standard JMS library because it uses the `jakarta.jms` API; the non-portable parts are the provider JAR, URL, authentication, and capabilities.

## 9. Without a Starter: Providing ConnectionFactory to Spring Yourself

Spring JMS needs a `jakarta.jms.ConnectionFactory` bean. With Boot, a starter may create it for you; with a plain Spring Framework application or a provider not directly auto-configured by Boot, you must create the bean using the vendor client class or look it up from JNDI/container.

Skeleton configuration example (illustrating a factory bean already provided by the container/provider):

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class JmsWiring {
    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

This class is complete only when a matching `ConnectionFactory` bean already exists, created by container/vendor configuration. It **does not** implement a provider itself. When `@JmsListener` does not specify `containerFactory`, Spring looks for a bean named `jmsListenerContainerFactory`. In Boot, much of this auto-configuration is already provided; you do not necessarily have to declare every bean manually.

### JNDI, Pooling, and Connection Management

- An application server can provide a `ConnectionFactory` via JNDI/resource adapter. In that case, use the **managed factory** to match container-managed transactions/security; do not arbitrarily create a parallel native client.
- Spring's `CachingConnectionFactory` helps reuse connections/sessions; provider pools like `pooled-jms` have different pooling policies. Choose and measure according to workload rather than assuming "the bigger the pool, the better."
- If durable subscriptions with a client ID are needed, you must check connection/client ID management rules and concurrency; shared subscriptions and unshared durable subscriptions behave differently.
- With multiple providers in the same context, use `@Qualifier` or separate factories for publishers/listeners. Only pick a single default `ConnectionFactory` when the application genuinely has one logical broker.

## 10. What Should Compatibility Tests Verify?

A `connect()` test is necessary but insufficient. Run these sequentially on **the exact broker version, client, JDK, and intended deployment configuration**:

| Test level | Action | Pass criteria |
|---|---|---|
| **Build** | Resolve dependencies; compile importing `jakarta.jms.ConnectionFactory`. | No class conflicts, `NoSuchMethodError`, or `javax`/`jakarta` mismatch. |
| **Connection** | Connect to the real broker over the planned URL/protocol. | Correct host/port, handshake, authentication, TLS, and ACLs. |
| **Queue** | Send a `TextMessage` with an ID; receive and acknowledge it. | Payload, headers, properties, correlation ID, and acknowledgement are accurate. |
| **Topic** | Two independent subscriptions receive events; test shared/durable if needed. | Delivery per subscription; offline backlog behaves as contracted. |
| **Rollback/Retry** | Listener intentionally throws an exception; test redelivery and DLQ. | Retry count, duplicates, and poison messages follow policy. |
| **Transaction** | Verify JMS local transactions or XA/JTA if actually required. | Commit/rollback and failure boundaries are consistent; not just seeing `@Transactional`. |
| **Operations** | Kill/restart broker, drop network, hit quota, rotate credentials/certificates. | Reconnect, failover, timeouts, and recovery meet SLA targets. |
| **Load & observability** | Peak and sustained load tests; measure backlog/lag/redelivery. | Meets throughput/latency, no resource leaks, and sufficient logs/metrics for diagnosis. |

**Test critical features, not just advertised spec versions.** For example, basic consumers working with ActiveMQ Classic do not guarantee `shared durable subscription` is supported on the exact version you run. On a multi-protocol broker, a queue can carry a different routing type depending on the protocol; test the corresponding mapping as well.

### Minimum Verification Against a Real Environment

1. Use a **dev/test broker**, never test by deleting/truncating a production Queue.
2. Create destinations with clear names and the right Queue/Topic type; set a short TTL and message ID for tracing.
3. Send from Spring and receive in Spring; if integrating across languages, cross-send/receive with the other client.
4. Test offline clients, broker restarts, network partitions, and invalid authentication.
5. Record the tuple of **JDK + Spring Boot/Framework + provider client + broker version + protocol + security config + verified features**.

Only when this tuple has passed testing should the setup be considered "compatible" for your specific requirements; running in a lab is not proof of production equivalence.

## 11. Common Errors and How to Isolate Them

| Symptom | Likely cause | Check step |
|---|---|---|
| `package javax.jms does not exist` or fails to compile `jakarta.jms` | Wrong namespace for the imported API. | Check Spring major version, dependency tree, and imports; switch to the right client line. |
| `NoClassDefFoundError: javax/jms/...` in Boot 3 | Provider JAR or auxiliary library still uses `javax`. | Run `dependencyInsight`, identify the offending artifact, and replace with the Jakarta version. |
| `ClassCastException` or factory cannot be assigned to `jakarta.jms.ConnectionFactory` | Client implements an interface from a different namespace. | Check the vendor factory's actual interfaces; do not force-cast. |
| `No qualifying bean of type 'jakarta.jms.ConnectionFactory'` | Only JMS API present, missing starter/provider bean, or auto-config did not run. | Inspect the startup condition report and declare the proper starter/factory. |
| Connection refused or hangs during handshake | Broker not running, wrong endpoint/port, protocol, or firewall. | Check active listeners/acceptors, network reachability, and logs on both sides. |
| `JMSSecurityException`, TLS handshake failure | Wrong user, channel authority, truststore, or hostname/certificate. | Verify ACLs and TLS profile against vendor docs; do not log credentials. |
| Send succeeds, but listener does not receive | Wrong Queue/Topic type, different destination, missing subscription/selector, or transaction issue. | Verify routing type and listener factory, subscription, and broker metrics. |
| `UnsupportedOperationException` on a JMS API | Client/provider does not implement the required JMS feature. | Read the feature matrix for the exact version, test the API, and consider another provider. |
| Multiple `ConnectionFactory` beans cause ambiguous injection | Pulling multiple starters/providers or declaring an extra factory. | Remove redundant dependencies; if multi-broker, use `@Qualifier`/bean names. |
| Embedded broker tests pass, production fails | Embedded skips real networking/TLS/ACL/failover. | Test against a real broker with configuration matching the runtime environment. |

### Three Misconceptions to Correct Immediately

- **"Adding `jakarta.jms-api` is enough."** False: that is only the interface contract; you need a client implementation and a provider endpoint.
- **"The broker says it supports AMQP/JMS, so any client can connect."** False: JMS does not standardize a wire protocol; authentication, version negotiation, and feature mappings still differ.
- **"Spring Boot created `JmsTemplate`, so the broker is ready."** False: a bean existing at startup does not prove a connection was made, that you have Queue/Topic permissions, or that a round-trip succeeds. Run an integration test.

## 12. Scenario-Based Solution Selection Exercise

**Scenario A.** A new Spring Boot 3 application requiring JMS Queues/Topics, able to operate its own broker, wanting fast local testing.  
**Suggestion:** Start by evaluating **Artemis + `spring-boot-starter-artemis`**; create an embedded smoke test, then test a remote broker with TLS, durable subscribers, and failover if needed.

**Scenario B.** An organization has an ActiveMQ Classic 5.18 broker; a new application uses `jakarta.jms` and only connects remotely.  
**Suggestion:** Evaluate the transitional `activemq-client-jakarta` client on the exact 5.18.1+ branch or a plan to upgrade the broker/client to 6.x; do not use `activemq-client` 5.18.x `javax` as a Spring 6 factory; verify the exact APIs used and shared subscription limitations.

**Scenario C.** An environment already has an IBM MQ queue manager, full ACL/TLS standards, and licenses; Spring Boot 3 needs to connect.  
**Suggestion:** Use the **Jakarta client** and starter published by IBM as compatible with Boot 3; configure channel, TLS, and permissions, and verify queue manager version and failover instead of changing brokers unnecessarily.

**Scenario D.** A broker exposes an AMQP 1.0 endpoint; the Java team wants to use `@JmsListener` without a vendor driver.  
**Suggestion:** Evaluate **Qpid JMS 2.x** with a dedicated `ConnectionFactory`; prove the broker supports the needed JMS semantics. An arbitrary AMQP broker does not automatically guarantee all JMS features.

**Scenario E.** A system uses RabbitMQ with Spring AMQP and has no JMS requirements.  
**Suggestion:** Use `spring-boot-starter-amqp` and the Spring AMQP APIs; do not add a JMS layer simply because JMS also supports message queues.

## 13. Pre-Lock-In Dependency Checklist

- [ ] Chosen a **provider/broker** matching requirements, without confusing a client/JAR name with a broker.
- [ ] Confirmed **Spring + JDK + `javax.jms`/`jakarta.jms`** and a single client implementation in the right namespace.
- [ ] Confirmed the **protocol/port/transport** used by the client matches an acceptor/endpoint supported by the broker.
- [ ] Used the appropriate **BOM/version matrix** and inspected the runtime dependency tree.
- [ ] Tested **Queue/Topic** and the features actually used: shared/durable, selectors, TTL, transactions, redelivery, DLQ.
- [ ] Tested **TLS/auth/ACL** and HA/recovery mechanisms as required.
- [ ] Executed a send–receive round-trip in a near-production environment with metrics/logs for diagnostics.
- [ ] Recorded the **verified version matrix**; established an upgrade and security-patching plan.

## 14. Official References for Verification

- [Spring Framework — Using JMS, ConnectionFactory, resource handling](https://docs.spring.io/spring-framework/reference/integration/jms/using.html).
- [Spring Framework — Annotation-driven @JmsListener](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Boot 3.4 — JMS (ActiveMQ Classic, Artemis, configuration)](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html).
- [Spring Boot 3.5 — Managing Dependencies](https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html).
- [Apache ActiveMQ Artemis — JMS/Jakarta client classpath](https://artemis.apache.org/components/artemis/documentation/latest/client-classpath).
- [Apache ActiveMQ Artemis — Protocols and interoperability](https://artemis.apache.org/components/artemis/documentation/latest/protocols-interoperability.html).
- [Apache ActiveMQ Classic — Jakarta Messaging/JMS support matrix](https://activemq.apache.org/components/classic/documentation/jms2).
- [IBM MQ — Jakarta Messaging client overview](https://www.ibm.com/docs/en/ibm-mq/10.0.x?topic=messaging-mq-classes-jakarta-overview).
- [IBM MQ JMS Spring starter — README and version support](https://github.com/ibm-messaging/mq-jms-spring).
- [Apache Qpid JMS — Jakarta Messaging AMQP 1.0 client](https://qpid.apache.org/components/jms/index.html).
