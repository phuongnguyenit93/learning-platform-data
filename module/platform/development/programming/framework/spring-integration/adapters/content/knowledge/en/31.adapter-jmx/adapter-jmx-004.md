# JMX notification-publishing adapter

## 1. Problem: turning a Spring Message into a JMX Notification

A Spring Integration service receives alerts from HTTP, JMS, Kafka, or database checks. The application wants to **publish these alerts to JVM management tools** such as JConsole, a JMX client, or another Spring Integration JMX notification listener. The system needs to transform data already on a `MessageChannel` into a `javax.management.Notification` and register a **publisher MBean** with an explicit `ObjectName`.

The **JMX notification-publishing adapter** solves this problem. It is a Spring Integration **outbound channel adapter**: when receiving a Spring `Message<?>` from its input channel, the adapter uses `NotificationPublishingMessageHandler` to create a JMX `Notification` and emit it through the JMX `NotificationPublisher`/`MBeanExporter` mechanism. It does **not** send JMS/Kafka records itself, does not invoke an operation on a remote MBean, and does not require a poller.

The lesson **“JMX notification-publishing adapter”** belongs to the **Adapter JMX** chapter, **SPRING_INTEGRATION_ADAPTERS** module. This module covers connecting external systems to Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`, practicing file, SFTP, HTTP, JMS, AMQP, Kafka, and database flows alongside message contracts, errors, and connection lifecycles. JMX notification publishing is a **JVM-management outbound endpoint** in that same integration system.

After this lesson, you will be able to:

1. Distinguish `NotificationPublishingMessageHandler` from inbound `NotificationListeningMessageProducer`, attribute polling, and operation-invoking gateways.
2. Understand the roles of `MBeanExporter`, `NotificationPublisherAware`, the publisher delegate, `MBeanServer`, and `ObjectName`.
3. Configure the native `int-jmx:notification-publishing-channel-adapter` and `<context:mbean-export/>` in XML.
4. Write Java configuration using `@EnableMBeanExport`, `NotificationPublishingMessageHandler`, `MessageChannel`, and `IntegrationFlow`.
5. Explain accurately how the default adapter maps **String payload → Notification.message** and **non-String payload → Notification.userData**.
6. Configure the notification `type` via the `JmxHeaders.NOTIFICATION_TYPE` header or `default-notification-type`, and understand their precedence.
7. Customize mapping with `OutboundMessageMapper<Notification>` to control source, sequence, timestamp, text, and userData.
8. Write JUnit tests with a local `MBeanServer.addNotificationListener(...)` to capture real notifications from a Spring channel.
9. Design error handling, backpressure, lifecycle, JMX security, and durability/replay boundaries honestly.
10. Bring JMX notifications into a monitoring system without confusing them with broker event delivery or business commits.

**Key point:** The Spring Integration outbound JMX publisher turns **one Spring message** into **one JMX notification publication**. It is a management boundary, not a durable queue or end-to-end exactly-once transport.

## 2. Architecture: Spring Integration → JMX MBean → listener

~~~mermaid
flowchart LR
    SRC["HTTP / JMS / Kafka / DB<br/>or internal service"]
    ROUTE["IntegrationFlow<br/>validate/route"]
    CH["jmx.notifications.out<br/>MessageChannel"]
    AD["NotificationPublishingMessageHandler<br/>outbound adapter"]
    PUB["NotificationPublisher<br/>MBeanExporter"]
    SERVER[("MBeanServer<br/>ObjectName publisher")]
    L1["JMX NotificationListener"]
    L2["JConsole / monitoring"]
    SRC --> ROUTE --> CH --> AD --> PUB --> SERVER
    SERVER --> L1
    SERVER --> L2
~~~

Execution flow:

1. An endpoint or service creates a Spring `Message<?>` with payload and headers.
2. `IntegrationFlow` can validate schemas, classify severity, and filter out events that should not be published.
3. The message is sent to the input `MessageChannel` dedicated to the JMX outbound adapter.
4. `NotificationPublishingMessageHandler` uses a mapper to construct a `javax.management.Notification`.
5. The handler emits the notification via Spring's `NotificationPublisher`, provided through a publisher MBean delegate registered with `MBeanExporter`.
6. `MBeanServer` dispatches the notification to `NotificationListener`s registered on that `ObjectName`.
7. JMX consumers read `type`, `source`, `sequenceNumber`, `timeStamp`, `message`, and `userData` per contract.

**Never assume** a notification reached every client just because the handler finished calling publish. Listeners might not be registered yet, remote clients may be disconnected, or callbacks may fail; JMX does not keep a default backlog.

### 2.1. Data direction is outbound

~~~text
Spring MessageChannel
      ↓
NotificationPublishingMessageHandler
      ↓
JMX Notification Publisher MBean
      ↓
JMX NotificationListener(s)
~~~

Reversed direction:

~~~text
JMX MBean emits Notification
      ↓
NotificationListeningMessageProducer
      ↓
Spring MessageChannel
~~~

The first is the **outbound publishing adapter**; the second is the **inbound listening adapter**. Do not let similar names cause you to configure the wrong direction.

### 2.2. Both adapters can be used in the same application

For example, service A has a Spring Integration outbound publisher and service B has a JMX inbound listener (if both can reach the right `MBeanServer`/remote connector). They form a monitoring **bridge** topology. However, to reliably transmit business events between two JVMs, prefer HTTP/JMS/AMQP/Kafka or an event broker rather than using JMX Notifications as a durable transport.

## 3. What is a JMX Notification?

JMX manages objects using `MBeanServer` and `ObjectName`. A notification is a `javax.management.Notification` instance, typically carrying:

| API | Meaning | Contract notes |
| --- | --- | --- |
| `getType()` | Notification type, e.g. `demo.queue.depth.warning`. | Should be dot-delimited and stable/versioned. |
| `getSource()` | Notification emission source. | May be an `ObjectName` or another object depending on mapper/broadcaster. |
| `getSequenceNumber()` | Sequence number assigned by publisher/mapper. | Not a global business event ID by default. |
| `getTimeStamp()` | Time the notification was created/emitted. | Not necessarily when the business event occurred. |
| `getMessage()` | Text description. | Not a good schema for strict data parsing. |
| `getUserData()` | Extra data, type `Object`. | Validate type, compatibility, and security. |

Example of manually constructing a JMX notification:

~~~java
import javax.management.Notification;
import javax.management.ObjectName;

ObjectName publisherName =
        new ObjectName("demo.integration:type=AlarmPublisher,name=Orders");

Notification warning = new Notification(
        "demo.queue.depth.warning",
        publisherName,
        42L,
        System.currentTimeMillis(),
        "Orders queue depth exceeded threshold");

warning.setUserData(Integer.valueOf(125));
~~~

**Note:** `Notification` is just the JMX event structure. Constructing the object does not emit it; you must call JMX `NotificationPublisher.sendNotification(...)` or a suitable broadcaster. In this lesson, the Spring Integration handler performs the publishing step.

### 3.1. MBeanExporter vs. MBeanServer

`MBeanServer` is the registry and dispatch engine. Spring's `MBeanExporter` exports/registers managed beans and supplies the publisher delegate with a `NotificationPublisher`.

Spring Integration's `NotificationPublishingMessageHandler` requires an `MBeanExporter` available in the context; the handler internally owns a **`PublisherDelegate`** registered under the publisher `ObjectName`. Thus you **do not need to write a custom notification-emitting MBean** in the minimal setup.

### 3.2. Publisher ObjectName

Example:

~~~text
demo.integration:type=AlarmPublisher,name=Orders
~~~

This is a JMX `ObjectName`, not a Spring bean ID and not an MQTT topic. It must be a concrete, valid name that does not collide with another MBean on the same `MBeanServer`.

### 3.3. NotificationPublisherAware and PublisherDelegate

Spring Framework supports the `org.springframework.jmx.export.notification.NotificationPublisherAware` interface. When a managed bean is exported properly, it receives a `NotificationPublisher` to call `sendNotification(Notification)`.

Spring Integration encapsulates this detail inside `NotificationPublishingMessageHandler.PublisherDelegate`. Normal usage configures the handler and `MBeanExporter`, **not** calling `delegate.setNotificationPublisher(...)` manually.

## 4. Comparison with other JMX endpoints

| Spring Integration JMX endpoint | Direction | Trigger | Meaning |
| --- | --- | --- | --- |
| `notification-publishing-channel-adapter` | Outbound | Spring message arrives on channel. | Creates and emits a JMX Notification. |
| `notification-listening-channel-adapter` | Inbound | JMX Notification callback. | Receives Notification into a Spring Message. |
| `attribute-polling-channel-adapter` | Inbound | Scheduled Spring poller. | Reads one MBean attribute. |
| `tree-polling-channel-adapter` | Inbound | Scheduled Spring poller. | Captures a snapshot of multiple MBeans. |
| `operation-invoking-channel-adapter` | Outbound | Spring message arrives on channel. | Invokes a JMX operation, no reply needed. |
| `operation-invoking-outbound-gateway` | Outbound request-reply | Spring request. | Invokes a JMX operation and returns response. |
| `JmsSendingMessageHandler` / Kafka producer | Outbound transport | Spring message. | Sends to a messaging broker with its own protocol. |

**Notification** and **operation** are distinct concepts: notifications publish to listeners; operations invoke management methods on an MBean. If you need the return value of `resetQueue()`, do not try to fake RPC with a notification publisher.

## 5. Dependencies and Spring Integration versions

The examples in this lesson use **Java 17+, Spring Boot / Spring Integration 6.x**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-jmx</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Use the **Spring Boot BOM** to select compatible framework versions; never mix `spring-integration-core 6.x` with `spring-integration-jmx 7.x`.

### 5.1. Package changes between 6.x and 7.x

| Type | Spring Integration 6.x | Spring Integration 7.x |
| --- | --- | --- |
| `NotificationPublishingMessageHandler` | `org.springframework.integration.jmx.NotificationPublishingMessageHandler` | `org.springframework.integration.jmx.outbound.NotificationPublishingMessageHandler` |
| `JmxHeaders` | `org.springframework.integration.jmx.JmxHeaders` | Check Javadocs for your exact version; do not assume all JMX classes moved into outbound. |
| `MBeanExporter` | `org.springframework.jmx.export.MBeanExporter` | Spring Framework JMX class, not Spring Integration outbound. |
| `@EnableMBeanExport` | `org.springframework.context.annotation.EnableMBeanExport` | Spring Framework annotation. |

If Java import errors occur after upgrading, check the Javadocs for your exact dependency version. Do not blindly change every `org.springframework.integration.jmx` to `jmx.outbound`: headers, inbound sources, and config classes live in different packages.

### 5.2. Why isn't spring-boot-starter-actuator alone enough?

Actuator exposes health/metrics endpoints, but does not automatically create `NotificationPublishingMessageHandler` or the outbound JMX adapter. To use the native adapter, you need `spring-integration-jmx` and an `MBeanExporter` configured in the Spring context.

## 6. XML namespace: native notification-publishing channel adapter

Minimal configuration from the Spring Integration Reference:

~~~xml
<context:mbean-export/>

<int-jmx:notification-publishing-channel-adapter
        id="queueAlarmPublisher"
        channel="jmx.notifications.out"
        object-name="demo.integration:type=AlarmPublisher,name=Orders"/>
~~~

Three key elements to understand:

1. `<context:mbean-export/>` registers Spring's `MBeanExporter`.
2. `channel="jmx.notifications.out"` is the **input channel** of the outbound adapter.
3. `object-name` is the publisher MBean name that the handler registers on the JMX server.

**No poller is needed** on this outbound adapter: whenever a Spring message is sent to the channel, the handler creates and publishes the notification.

### 6.1. Full XML context

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:int-jmx="http://www.springframework.org/schema/integration/jmx"
       xsi:schemaLocation="
          http://www.springframework.org/schema/beans
          https://www.springframework.org/schema/beans/spring-beans.xsd
          http://www.springframework.org/schema/context
          https://www.springframework.org/schema/context/spring-context.xsd
          http://www.springframework.org/schema/integration
          https://www.springframework.org/schema/integration/spring-integration.xsd
          http://www.springframework.org/schema/integration/jmx
          https://www.springframework.org/schema/integration/jmx/spring-integration-jmx.xsd">

    <context:mbean-server id="mbeanServer"/>

    <context:mbean-export server="mbeanServer"/>

    <int:channel id="jmx.notifications.out"/>

    <int-jmx:notification-publishing-channel-adapter
            id="queueAlarmPublisher"
            channel="jmx.notifications.out"
            object-name="demo.integration:type=AlarmPublisher,name=Orders"
            default-notification-type="demo.queue.alarm"/>
</beans>
~~~

This is a **native XML** configuration; `MBeanExporter` is linked to `mbeanServer` in the context. It does not declare a separate `<bean class="QueuePublisher">` because the Spring Integration handler uses its internal publisher delegate via the exporter mechanism.

### 6.2. Missing MBeanExporter causes endpoint initialization failure

`NotificationPublishingMessageHandler` looks up a bean of type `MBeanExporter` in the Spring bean factory during initialization; missing the exporter is a configuration error. Having only an `MBeanServer` is not equivalent to having an `MBeanExporter`; creating a server does not ensure the publisher delegate is exported and given a `NotificationPublisher`.

### 6.3. default-notification-type is a fallback

~~~xml
<int-jmx:notification-publishing-channel-adapter
        id="queueAlarmPublisher"
        channel="jmx.notifications.out"
        object-name="demo.integration:type=AlarmPublisher,name=Orders"
        default-notification-type="demo.queue.alarm"/>
~~~

If the Spring message **lacks** the `JmxHeaders.NOTIFICATION_TYPE` header, the default mapper uses `demo.queue.alarm`. If the message provides a valid type header, **the header takes precedence**.

### 6.4. Do not declare two adapters with the same ObjectName

On the same `MBeanServer`, two publishing handlers with the same `demo.integration:type=AlarmPublisher,name=Orders` `ObjectName` will collide on MBean registration. If you want two alert categories, send them to **one handler** and vary the notification type via header rather than creating another publisher with the same name.

## 7. Default contract: String payload and userData

The Spring Integration Reference defines the default mapping:

| Spring message payload | JMX Notification result | Meaning |
| --- | --- | --- |
| `String` | Used as `Notification.message` text. | Suitable for short, readable messages in JConsole. |
| `Integer`/record/DTO/`Map`/other objects | Placed into `Notification.userData`. | Carries structured data; requires schema/type contract. |
| `JmxHeaders.NOTIFICATION_TYPE` header | Used as `Notification.type` when present. | Overrides the default type. |
| No type header, adapter has `default-notification-type` | Uses the default type. | Suits endpoints publishing a single category. |
| Neither type header nor default type | Default mapper has no valid type. | One of the two must be provided before sending. |

Example sending text:

~~~java
MessageBuilder.withPayload(
        "Orders queue exceeded warning threshold")
    .setHeader(JmxHeaders.NOTIFICATION_TYPE,
            "demo.queue.depth.warning")
    .build();
~~~

Sending this payload to the outbound channel creates a JMX Notification with the corresponding `message` text and the `type` from the header.

Sending a DTO:

~~~java
public record QueueAlarm(
        String queueName,
        int depth,
        String severity,
        String eventId) implements java.io.Serializable {
}

QueueAlarm alarm =
        new QueueAlarm("Orders", 125, "CRITICAL", "evt-1001");

MessageBuilder.withPayload(alarm)
        .setHeader(JmxHeaders.NOTIFICATION_TYPE,
                "demo.queue.depth.critical")
        .build();
~~~

Because the payload is **not a String**, the default mapper assigns the DTO to `userData`. When a JMX client in another JVM receives this object via a remote connector, pay attention to classpath and Java serialization/deserialization compatibility; never assume a remote monitoring tool has the `QueueAlarm` class. For better interoperability, use primitives/`CompositeData` or a custom mapper producing safe data.

### 7.1. Type precedence: easy-to-remember example

~~~text
Adapter default-notification-type = demo.queue.alarm
Message header NOTIFICATION_TYPE  = demo.queue.depth.critical

JMX Notification type = demo.queue.depth.critical
~~~

If the message omits the header, the result is `demo.queue.alarm`. Do not use Spring's `MessageHeaders.CONTENT_TYPE` or `MessageHeaders.ID` in place of the JMX notification type.

### 7.2. Types should be dot-delimited names with a version policy

An example set of types:

~~~text
demo.queue.depth.warning
demo.queue.depth.critical
demo.queue.depth.recovered
demo.connection.pool.exhausted
demo.integration.route.failed
~~~

The type name is a **contract for listeners**. Do not embed sensitive values or high-cardinality IDs in the type; place them in governed `userData`/schemas. When changing meaning or schema, define a versioning/compatibility policy rather than altering text ad hoc.

### 7.3. Notification.message should not be the primary payload contract

If a downstream parser has to extract queue and depth from a sentence like `"Orders queue exceeded threshold 125"`, it breaks easily when wording changes. Use `userData` with explicit fields (`queueName`, `depth`, `eventId`, `schemaVersion`) and reserve `message` for display, not the reverse.

### 7.4. Sequence number is not a durable eventId

JMX `Notification.sequenceNumber` provides relative ordering/distinction within a publisher runtime; do not use it as a system-wide business event ID. It can reset on restart, differs across JVMs, and cannot replace a unique key if downstream persists/deduplicates. Carry an explicit `eventId` when the business needs idempotency.


## 8. Java configuration: native NotificationPublishingMessageHandler

Spring Integration provides `NotificationPublishingMessageHandler`. You can use it directly as a Spring `MessageHandler` inside `IntegrationFlow` without calling `NotificationPublisher` yourself. The example below uses **Spring Integration 6.x**; in 7.x, change the handler import to `org.springframework.integration.jmx.outbound.NotificationPublishingMessageHandler`.

### 8.1. Source code layout

~~~text
src/main/java/demo/jmxpublish/
    JmxPublishApplication.java
    JmxPublishingConfiguration.java
    QueueAlarm.java
    QueueAlarmSender.java

src/test/java/demo/jmxpublish/
    JmxNotificationPublishingTest.java
~~~

These classes share the `demo.jmxpublish` package. Each `public` top-level class/record should reside in a matching filename.

### 8.2. Native Java config with MBeanExporter

~~~java
package demo.jmxpublish;

import java.lang.management.ManagementFactory;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jmx.NotificationPublishingMessageHandler;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@EnableMBeanExport(server = "mbeanServer")
class JmxPublishingConfiguration {

    static final String PUBLISHER_NAME =
            "demo.integration:type=AlarmPublisher,name=Orders";

    @Bean(name = "mbeanServer")
    MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean(name = "jmx.notifications.out")
    MessageChannel jmxOutboundChannel() {
        return new DirectChannel();
    }

    @Bean
    NotificationPublishingMessageHandler jmxPublisherHandler()
            throws Exception {

        var handler = new NotificationPublishingMessageHandler(
                new ObjectName(PUBLISHER_NAME));

        handler.setDefaultNotificationType(
                "demo.queue.alarm");

        return handler;
    }

    @Bean
    IntegrationFlow jmxPublishingFlow(
            NotificationPublishingMessageHandler handler) {

        return IntegrationFlow
                .from("jmx.notifications.out")
                .handle(handler)
                .get();
    }
}
~~~

**API-accurate explanation:**

1. `@EnableMBeanExport(server = "mbeanServer")` provides a Spring `MBeanExporter` capable of exporting MBeans, equivalent to `<context:mbean-export/>`.
2. `@Bean mbeanServer()` selects the JVM's platform `MBeanServer`; the exporter and JMX listener tests must reference this same server.
3. `new NotificationPublishingMessageHandler(new ObjectName(...))` identifies the publisher delegate registered by the handler.
4. `setDefaultNotificationType(...)` provides the fallback type when a Spring message lacks `JmxHeaders.NOTIFICATION_TYPE`.
5. `DirectChannel` is the outbound input; when sending to the channel, `IntegrationFlow` invokes the handler and emits the JMX Notification.
6. `.handle(handler)` reuses the same handler bean—do not register two separate handlers with the same `ObjectName`.
7. `MBeanExporter` is created by the annotation, so **do not** declare an additional manual `MBeanExporter` unless you understand registration collisions.
8. The demo emits JMX notifications within the local JVM only; remote clients require a separate connector and security.

### 8.3. Do not confuse with an arbitrary @ManagedResource

The handler manages an internal `PublisherDelegate`. `MBeanExporter` registers the delegate under the handler's `ObjectName` and injects `NotificationPublisher` through JMX publisher support. If you also export a `QueueAlarmMBean` bean under **that exact same ObjectName**, registration fails because an MBean already exists. Keep naming ownership unique.

### 8.4. Application entry point

~~~java
package demo.jmxpublish;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JmxPublishApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                JmxPublishApplication.class, args);
    }
}
~~~

When the configuration in the same package is component-scanned, the app creates the `MBeanServer`, exporter, message channel, native publishing handler, and flow. No notification is emitted merely because the application started; a Spring message must be sent to the channel.

## 9. Java API for a notification-sending service

### 9.1. QueueAlarm.java

~~~java
package demo.jmxpublish;

import java.io.Serializable;

public record QueueAlarm(
        String queueName,
        int depth,
        String severity,
        String eventId) implements Serializable {

    public QueueAlarm {
        if (queueName == null || queueName.isBlank()) {
            throw new IllegalArgumentException("queueName is missing");
        }
        if (depth < 0 || eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("Invalid QueueAlarm");
        }
    }
}
~~~

This record demonstrates structured `userData`. Implementing `Serializable` does **not** guarantee a remote JMX client can deserialize an application Java class it does not possess. Production should consider `CompositeData`/simple types or JSON/string schemas when interoperating across different tools.

### 9.2. QueueAlarmSender.java

~~~java
package demo.jmxpublish;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.jmx.JmxHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class QueueAlarmSender {

    private final MessageChannel outbound;

    public QueueAlarmSender(
            @Qualifier("jmx.notifications.out")
            MessageChannel outbound) {
        this.outbound = outbound;
    }

    public boolean publishText(String text) {
        return outbound.send(
                MessageBuilder.withPayload(text).build());
    }

    public boolean publishAlarm(QueueAlarm alarm) {
        String type = switch (alarm.severity()) {
            case "WARNING" -> "demo.queue.depth.warning";
            case "CRITICAL" -> "demo.queue.depth.critical";
            case "RECOVERED" -> "demo.queue.depth.recovered";
            default -> throw new IllegalArgumentException(
                    "Invalid severity: " + alarm.severity());
        };

        return outbound.send(MessageBuilder.withPayload(alarm)
                .setHeader(JmxHeaders.NOTIFICATION_TYPE, type)
                .build());
    }
}
~~~

Registering the sender bean in the same Java config:

~~~java
@Bean
QueueAlarmSender queueAlarmSender(
        @Qualifier("jmx.notifications.out") MessageChannel channel) {
    return new QueueAlarmSender(channel);
}
~~~

When using this `@Bean` snippet, import `org.springframework.beans.factory.annotation.Qualifier` in the configuration file. In production, you can annotate the sender with `@Service` instead of `@Bean`; **choose one** instantiation mechanism to avoid creating two unnecessary instances.

### 9.3. Two calls for two Notification styles

~~~java
sender.publishText("Orders queue reached warning level");

sender.publishAlarm(new QueueAlarm(
        "Orders", 125, "CRITICAL", "evt-orders-001"));
~~~

The first call has a **String payload** and no `NOTIFICATION_TYPE` header, so it uses default type `demo.queue.alarm` and places the text in `Notification.message`.

The second call has a **record payload** and header type `demo.queue.depth.critical`. JMX `Notification.userData` holds the record, while `type` comes from the header.

### 9.4. Boolean send() is not confirmation from all JMX listeners

`MessageChannel.send(...)` indicates whether the channel accepted/dispatched the message per channel contract; with `DirectChannel` and a synchronous handler, handler exceptions propagate. However, returning `true` is not a JMX acknowledgment from all JConsole clients, nor does it provide retention or replay guarantees. Never interpret it as "the alert was handled by a human."

## 10. Java test: registering a JMX NotificationListener on the publisher MBean

This is the most practical test: **no broker or remote connector needed**, while exercising the real `MBeanServer` and Spring Integration outbound publisher in the same JVM.

### 10.1. Testing wiring, type fallback, and String payloads

~~~java
package demo.jmxpublish;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.jmx.JmxHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = JmxPublishingConfiguration.class)
class JmxNotificationPublishingTest {

    @Autowired
    MBeanServer server;

    @Autowired
    @Qualifier("jmx.notifications.out")
    MessageChannel outbound;

    private final BlockingQueue<Notification> notifications =
            new LinkedBlockingQueue<>();

    private ObjectName publisherName;

    private NotificationListener listener;

    @BeforeEach
    void subscribe() throws Exception {
        publisherName = new ObjectName(
                JmxPublishingConfiguration.PUBLISHER_NAME);

        assertTrue(server.isRegistered(publisherName));

        listener = (notification, handback) ->
                notifications.offer(notification);

        server.addNotificationListener(
                publisherName, listener, null, null);
    }

    @AfterEach
    void unsubscribe() throws Exception {
        if (publisherName != null && listener != null
                && server.isRegistered(publisherName)) {
            server.removeNotificationListener(
                    publisherName, listener);
        }
        notifications.clear();
    }

    private Notification nextNotification() throws Exception {
        Notification notification =
                notifications.poll(2, TimeUnit.SECONDS);
        assertNotNull(notification);
        return notification;
    }

    @Test
    void stringPayloadUsesDefaultTypeAndMessageText()
            throws Exception {
        assertTrue(outbound.send(
                MessageBuilder.withPayload(
                        "Orders queue exceeded threshold")
                        .build()));

        Notification event = nextNotification();

        assertEquals("demo.queue.alarm", event.getType());
        assertEquals(
                "Orders queue exceeded threshold",
                event.getMessage());
    }

    @Test
    void headerNotificationTypeOverridesFallback()
            throws Exception {
        var message = MessageBuilder
                .withPayload("Queue recovered")
                .setHeader(JmxHeaders.NOTIFICATION_TYPE,
                        "demo.queue.depth.recovered")
                .build();

        assertTrue(outbound.send(message));

        Notification event = nextNotification();
        assertEquals(
                "demo.queue.depth.recovered",
                event.getType());
        assertEquals("Queue recovered", event.getMessage());
    }

    @Test
    void objectPayloadBecomesUserData()
            throws Exception {
        QueueAlarm payload = new QueueAlarm(
                "Orders", 125, "CRITICAL", "evt-001");

        var message = MessageBuilder
                .withPayload(payload)
                .setHeader(JmxHeaders.NOTIFICATION_TYPE,
                        "demo.queue.depth.critical")
                .build();

        assertTrue(outbound.send(message));

        Notification event = nextNotification();
        assertEquals(
                "demo.queue.depth.critical",
                event.getType());
        assertEquals(payload, event.getUserData());
        assertTrue(event.getSequenceNumber() >= 0);
    }
}
~~~

**What the test proves:**

- The publisher delegate is registered on the right `MBeanServer` under `ObjectName`.
- `MBeanServer.addNotificationListener(...)` actually receives JMX notifications emitted by the Spring Integration handler.
- A String payload is placed into the Notification's text.
- `JmxHeaders.NOTIFICATION_TYPE` overrides the default type.
- A non-String record payload becomes `userData`.

### 10.2. Limitations of the JUnit test

- The test only proves local publication and listener registration while the Spring context is running; it does **not** prove remote JMX network reliability or durable replay.
- `BlockingQueue.poll(2, TimeUnit.SECONDS)` is a **bounded wait** to accommodate different scheduler/notification callback implementations, not a business retry.
- `@AfterEach` must remove the listener to prevent duplicate callbacks and memory leaks.
- Running multiple test contexts with the same `ObjectName` on the platform server can trigger `InstanceAlreadyExistsException`. Use per-test ObjectNames or serialize tests / clean up contexts.
- Sequence number is runtime metadata; do not hard-assert that the first notification always equals 1 across shared contexts or test ordering.
- The test code above targets Spring Integration **6.x**; for 7.x, update the `NotificationPublishingMessageHandler` import in the configuration.

### 10.3. Testing missing MBeanExporter

In a separate test context, create `NotificationPublishingMessageHandler` **without** an `MBeanExporter`. Because the handler needs the exporter to register its delegate, configuration must fail at startup rather than silently accepting messages and dropping JMX notifications. Assert that context startup throws an exception with the corresponding cause instead of waiting forever for a message that never arrives.

### 10.4. Testing a listener registered after the event was emitted

Send a notification **before** calling `addNotificationListener`, and only attach the listener afterward. By default, no broker replays old notifications. This illustrates the durability boundary, unlike a Kafka consumer replaying from a log.

## 11. MBeanExporter and PublisherDelegate lifecycle

### 11.1. Who registers the publisher MBean?

In the native configuration, `NotificationPublishingMessageHandler` uses a delegate registered with Spring's `MBeanExporter` when the handler initializes. The JMX `ObjectName` comes from the constructor or XML `object-name`.

~~~mermaid
sequenceDiagram
    participant C as Spring Context
    participant E as MBeanExporter
    participant H as NotificationPublishingMessageHandler
    participant S as MBeanServer
    participant L as JMX Listener
    C->>E: Create MBeanExporter
    C->>H: Initialize handler
    H->>E: Register PublisherDelegate + ObjectName
    E->>S: Export managed resource
    L->>S: addNotificationListener(ObjectName)
    C->>H: Spring Message arrives
    H->>E: Publish Notification
    S-->>L: handleNotification(...)
~~~

The diagram illustrates responsibilities without guaranteeing exact callback/thread scheduling across all `MBeanServer` implementations.

### 11.2. Do not collide on ObjectName with another MBean

If you create a `@ManagedResource(objectName = "demo.integration:type=AlarmPublisher,name=Orders")` bean **and** the native handler uses the same `ObjectName`, registration will collide. Only one owner should export each `ObjectName`. If you want an MBean that both exposes custom attributes and emits notifications, design a dedicated custom MBean/broadcaster rather than adding a native publisher with the same name.

### 11.3. Multiple MBeanExporters in one context

An application may have both Spring Core's `MBeanExporter` and `IntegrationMBeanExporter` for managing Spring Integration components. Those are two related yet distinct roles. The handler needs an available exporter, and when multiple exporters exist, verify exporter/server selection on your framework version and bean graph; avoid accidentally registering the publisher on server A while listeners listen on server B.

### 11.4. Application shutdown

When the context closes, the exporter and handlers must release MBean registrations. The platform `MBeanServer` lives as long as the JVM and should not be torn down just because one endpoint stops. If the app restarts in the same JVM/test context, ensure exporter cleanup so stale `ObjectName`s are not left behind.

### 11.5. MBeanPublisher only emits to currently registered listeners

There are no "subscriber groups," "consumer offsets," or "retained notifications" as in a message broker. The publisher delegate does not maintain an offline listener list or ensure reconnecting clients receive missed events. When compliance auditing is required, persist the notification/business event to a durable store **before or alongside** publication by explicit design.

## 12. Customizing mapping: OutboundMessageMapper<Notification>

The default mapper is convenient for simple text or records. When you need control over `source`, `sequenceNumber`, `timeStamp`, `message`, and `userData`, or want to normalize the payload into a simpler DTO, use `NotificationPublishingMessageHandler.setNotificationMapper(...)`.

### 12.1. Custom mapper example

~~~java
package demo.jmxpublish;

import java.util.concurrent.atomic.AtomicLong;

import javax.management.Notification;
import javax.management.ObjectName;

import org.springframework.integration.jmx.JmxHeaders;
import org.springframework.integration.jmx.NotificationPublishingMessageHandler;
import org.springframework.messaging.Message;

class CustomNotificationFactory {

    private final AtomicLong sequence = new AtomicLong();

    NotificationPublishingMessageHandler newHandler()
            throws Exception {

        ObjectName publisherName =
                new ObjectName(
                        JmxPublishingConfiguration.PUBLISHER_NAME);

        var handler =
                new NotificationPublishingMessageHandler(
                        publisherName);

        handler.setNotificationMapper(
                message -> toNotification(
                        publisherName, message));

        return handler;
    }

    Notification toNotification(
            ObjectName publisherName, Message<?> springMessage) {

        Object header = springMessage.getHeaders().get(
                JmxHeaders.NOTIFICATION_TYPE);

        String type = header instanceof String s
                && !s.isBlank()
                    ? s : "demo.queue.alarm";

        Object payload = springMessage.getPayload();

        String text = payload instanceof String s
                ? s : "Structured queue alarm";

        var result = new Notification(
                type,
                publisherName,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                text);

        if (!(payload instanceof String)) {
            result.setUserData(payload);
        }

        return result;
    }
}
~~~

`setNotificationMapper` takes an `OutboundMessageMapper<Notification>`; the lambda converts the Spring `Message` into a proper JMX `Notification`. The sample mapper uses `AtomicLong` for sequence numbers. In production, add appropriate validation/schema/dedup logic and avoid putting arbitrary Java objects into remote `userData`.

### 12.2. Using the custom mapper instead of the default handler

Do not register **both** the default handler from section 8 and the custom handler from section 12.1 under the same `ObjectName`. Choose one configuration:

~~~java
@Bean
NotificationPublishingMessageHandler jmxPublisherHandler()
        throws Exception {

    return new CustomNotificationFactory().newHandler();
}
~~~

This `@Bean` method **replaces** `jmxPublisherHandler()` from section 8—it is not a second bean. The custom mapper `@Bean` decides its own fallback type; `setDefaultNotificationType(...)` applies only to the default mapper and does not automatically alter custom mapper logic.

### 12.3. Type validation and source identity

A custom mapper must ensure:

- `type` is a dot-delimited string from an allowlisted set of events.
- Source `ObjectName` has a single owner and a stable identity per JVM/node.
- Sequence increments per publisher instance, without claiming global ordering.
- `timeStamp` and business `occurredAt` are separate fields if events can be delayed.
- `userData` contains no secrets/PII and follows an explicit schema/serialization contract.
- Business `eventId` stays stable across retries.
- The handler has an error policy for invalid inputs rather than dropping notifications silently.

### 12.4. Do not equate reply-channel with a JMX ACK

The custom mapper returns a `Notification` for the handler to publish; it does not produce a Spring reply message carrying a JMX ACK. For true request-reply, use an appropriate gateway or a separate business acknowledgement protocol. Any "notification received" guarantee on the consumer must be designed and verified separately.

## 13. Notification listeners filtering by type and using handback

To make a JMX consumer receive only `demo.queue.depth.critical`:

~~~java
import javax.management.NotificationFilter;

NotificationFilter onlyCritical =
        notification ->
                "demo.queue.depth.critical"
                        .equals(notification.getType());
~~~

Then register it:

~~~java
server.addNotificationListener(
        publisherName,
        (notification, handback) -> {
            System.out.println(notification.getType());
            System.out.println(notification.getMessage());
        },
        onlyCritical,
        "critical-alert-consumer");
~~~

The `handback` object is **supplied by the subscriber when registering the listener**; it is neither the Spring message header `JmxHeaders.NOTIFICATION_TYPE` nor `Notification.userData`.

In Spring Integration, an inbound `NotificationListeningMessageProducer` can also listen to the publisher MBean. When connecting an outbound publisher to an inbound adapter in the same JVM, keep channel names and routes separate to avoid a message loop.

### 13.1. Feedback loops must be prevented

~~~text
Spring input → JMX publishing adapter
                     ↓
             JMX listening adapter
                     ↓
               Spring input (wrong!)
~~~

If the listener uncontrollably re-publishes the same message back to the input channel, it creates an infinite loop and spikes CPU/logs. Use separate routes, source/tenant policies, `eventId`/hop metadata, or filters so notifications are never fed back into the publisher.

### 13.2. NotificationFilter runs on the listener, not the publisher

A publisher may emit notifications of many types, and each listener decides which types to accept. To reduce load or block sensitive data at the source, validate and filter the **Spring message before publishing**, rather than expecting every listener to protect itself.


## 14. Spring Message contract and type/header design

JMX notification publishing is an **outbound side-effect** point. Messages sent to the channel should be treated as an explicit contract, not arbitrary Java objects.

### 14.1. Recommended input contract

| Element | Purpose | Rule |
| --- | --- | --- |
| `payload` | Text or structured details. | Validate size/format/type before publishing. |
| `JmxHeaders.NOTIFICATION_TYPE` | Classifies the JMX notification. | Dot-delimited, allowlisted, overrides default. |
| `eventId` in payload/business header | Idempotency and tracing. | Stable across retries; never regenerate a random ID per attempt. |
| `occurredAt` | When the business event happened. | Kept separate from JMX publish timestamp. |
| `sourceNode` | Emitting JVM/instance/cluster. | Do not rely solely on `ObjectName` across multiple JVMs. |
| `severity` | Alerting/routing rules. | Enum/allowlist; never parse free-form message text. |
| `schemaVersion` | Governs `userData` compatibility. | Versioned DTO; avoid silent meaning changes. |
| `correlationId` | Links spans/flows. | Useful for logs; does not replace `eventId`. |

If you only need to display a sentence, a `String` payload suffices. If downstream needs to read `depth`/`severity`, send a DTO with an explicit schema and ensure remote JMX clients can safely deserialize or map the data.

### 14.2. Why use a header type instead of hardcoding one default for every event?

The same publisher MBean can emit:

~~~text
demo.queue.depth.warning
demo.queue.depth.critical
demo.queue.depth.recovered
demo.queue.connection.lost
demo.queue.connection.recovered
~~~

Using a header lets the native handler handle multiple types without creating one publisher MBean per type. Keep the default type as a fallback for legacy messages or single-purpose adapters.

### 14.3. Do not conflate JMX types with HTTP status codes

`Notification.getType()` is a JMX contract string. Do not force it to equal a Kafka topic, Spring class name, or HTTP status `500`. You can maintain an explicit mapping from HTTP error category → JMX type, as application logic.

### 14.4. Avoid large object graphs in userData

The JMX API lets `userData` hold any `Object`, which does not mean you should send JPA entities with lazy proxies, Java exceptions with huge stack traces, database connections, or objects retaining sensitive references. Choose small, immutable, serializable DTOs with length bounds and redaction. Remote JMX crosses a serialization boundary that local tests do not fully exercise.

## 15. Distinguishing "publish accepted" from "notification consumed"

### 15.1. What does a successful send() call confirm?

~~~mermaid
sequenceDiagram
    participant SRC as Spring Service
    participant CH as MessageChannel
    participant HANDLER as JMX Publisher Handler
    participant JMX as MBeanServer
    participant L as JMX Listener
    SRC->>CH: Message<QueueAlarm>
    CH->>HANDLER: handleMessage(...)
    HANDLER->>JMX: sendNotification(...)
    JMX-->>L: handleNotification(...)
    CH-->>SRC: send(...) result
    Note over SRC,L: No business ACK or durable replay by default
~~~

The diagram simplifies the chain of responsibility and **does not promise that callbacks finish before `send()` returns** under every listener/connector setup. Local and remote JMX can have different dispatch semantics, and listener or network errors occur at separate boundaries.

### 15.2. Publishing succeeds even with no listeners yet

The publisher MBean can exist and emit notifications when zero subscribers are attached. When a listener registers late, it does not automatically receive previously emitted messages. This differs from durable queues/topics with retention, replay, and consumer offsets.

### 15.3. The publisher does not own listener subscriptions

JMX listeners register themselves via `MBeanServerConnection.addNotificationListener` (or an equivalent client tool). By default, the publisher does not know who is online, who succeeded, or who missed an event. Never report "alert delivered to all admins" based solely on `MessageChannel.send()`.

### 15.4. Add a durable layer when higher reliability is required

If an alert has business impact, such as "never lose an alarm when order fulfillment fails":

~~~text
Business transaction
   → persist alarm event + outbox row (same DB transaction)
   → relay/publisher
   → JMX notification (best-effort management)
   → in parallel send to Kafka/JMS/HTTP with separate retry/ACK
~~~

JMX serves only real-time observation; the **source of truth** is the outbox/audit store or a properly designed durable broker. Never try to turn a JMX publisher into a Kafka log.

## 16. Error handling: four error categories to separate

### 16.1. Startup configuration errors

| Error | Symptom | Fix |
| --- | --- | --- |
| Missing `MBeanExporter` | Publisher handler fails to initialize. | Enable `<context:mbean-export/>` or `@EnableMBeanExport`. |
| Invalid `ObjectName` | Exception constructing handler from `ObjectName`. | Validate JMX domain/key-properties and use a valid `ObjectName`. |
| Duplicate `ObjectName` | MBean registration collision. | Choose a unique owner and publisher name. |
| Exporter bound to wrong server | Listener on server A cannot see publisher on server B. | Align `MBeanServer`, exporter, and listener. |
| Missing module | JMX classes/namespace fail to load. | Add `spring-integration-jmx` aligned with the BOM. |
| Wrong major-version import | `NotificationPublishingMessageHandler` fails to resolve. | 6.x uses `jmx`; 7.x uses `jmx.outbound`. |

**Misconfigurations must fail fast.** Do not report "JMX publisher healthy" merely because other parts of the Spring application context started partially.

### 16.2. Input data errors

- Missing type header and no default type: the default mapper has no notification type.
- Type violates contract: consumers ignore or misroute it.
- Payload object incompatible with remote serialization: clients fail to decode it.
- Oversized text or PII in data: JMX clients/logs expose it.
- Null DTO fields or non-allowlisted severity: mapping error.

**Solution:** validate before the adapter, classify `INVALID_NOTIFICATION_TYPE`, `INVALID_PAYLOAD_SCHEMA`, `OVERSIZED_USERDATA`, and `UNSUPPORTED_REMOTE_TYPE`, and avoid retrying permanent errors repeatedly.

### 16.3. Errors at the JMX publisher/registration

After startup, unregistering the publisher MBean or changing exporter/connector lifecycles can cause publication to fail. An `IllegalStateException` from the publisher or a Spring messaging exception may be thrown depending on implementation/version. Never swallow errors and log "sent" on every branch.

In applications with multiple Spring contexts or hot reloads, verify that the handler and its publisher delegate still point to the right exporter and server. An `ObjectName` registered by other code on the server does not mean the native handler can take it over.

### 16.4. Listener-side errors do not trigger automatic business retries

A listener failing to process a notification does not send a negative acknowledgement causing the publisher to retry. `NotificationListener.handleNotification(...)` is not a JMS listener method with transaction rollback/requeue. Build retries at a durable downstream if strong guarantees are required.

### 16.5. Spring channel/handler errors

With `DirectChannel`, handler exceptions propagate back to the caller on the same thread. With `ExecutorChannel`, errors can happen after the sender already received `send(true)`; configure an error channel and monitoring for the async branch. Spring's `ErrorMessage`/`errorChannel` does not add replay for already-published JMX notifications.

## 17. Backpressure and notification bursts

A Spring service can generate thousands of warnings per second. JMX `NotificationPublisher` and monitoring clients are not generally designed as high-throughput event brokers.

~~~mermaid
flowchart LR
    EVENTS["10,000 Spring Messages / s"]
    FILTER{"Filter / coalesce"}
    CH["bounded channel / executor"]
    HANDLER["JMX publishing handler"]
    JMX["JMX MBeanServer"]
    CLIENTS["Monitoring clients"]
    EVENTS --> FILTER --> CH --> HANDLER --> JMX --> CLIENTS
~~~

### 17.1. Filter alerts before publishing

If a queue stays at `Depth=120` for 10 minutes, a polling flow running every 5 seconds produces 120 **samples**. If every sample emits the same `CRITICAL` notification, listeners suffer an alert storm. A stateful transformer/filter should emit only when severity transitions or on an approved cooldown reminder.

### 17.2. Hysteresis to prevent flapping

~~~text
NORMAL   → WARNING   when depth >= 80
WARNING  → NORMAL    when depth <= 65
WARNING  → CRITICAL  when depth >= 120
CRITICAL → WARNING   when depth <= 105
~~~

Thresholds are illustrative only. Hysteresis needs the previous state rather than checking `depth >= 80` on each message independently. If multiple instances emit alerts, local in-memory state does not guarantee a single cluster-wide notification; consider coordination or idempotency in the business layer.

### 17.3. DirectChannel vs. ExecutorChannel

| Channel | Characteristics | Risks |
| --- | --- | --- |
| `DirectChannel` | Dispatches handler synchronously on sender thread. | Heavy publisher/JMX callbacks can block the source. |
| `ExecutorChannel` | Runs handler on a task executor. | Async errors, queue saturation, dropped tasks; `send` returning `true` does not prove completion. |
| `QueueChannel` | Buffers between producer and downstream polling consumer. | In-memory queue is not crash-durable without a persistent store. |
| Broker adapter | Has dedicated protocol, retention, and ACK. | Requires operating the broker and idempotency. |

Simply adding `ExecutorChannel` does not make JMX notifications durable; choose bounded executors/queues, define reject/drop/backpressure policies, and monitor lag.

### 17.4. When to coalesce

For metrics moving from 90% to 91% to 92%, a single "CRITICAL" alert plus gauge updates may suffice. For security/audit events, do not drop or merge occurrences if every individual event matters for compliance. The contract dictates whether dropping or merging is allowed.

## 18. Remote JMX, TLS, and publication scope

**The demo publishes within the local JVM.** For clients outside the JVM to observe notifications, a JMX remote connector and proper security configuration are required. The native publishing adapter itself does not open a public TCP port.

### 18.1. Local and remote flows

~~~mermaid
flowchart LR
    FLOW["Spring JMX publisher"]
    SERVER[("Platform MBeanServer")]
    LOCAL["Local JMX listener"]
    CONNECTOR["JMX Remote Connector<br/>RMI/TLS/Auth"]
    REMOTE["Remote JMX client"]
    FLOW --> SERVER --> LOCAL
    SERVER --> CONNECTOR --> REMOTE
~~~

A local `MBeanServer` can still serve remote JMX if the server/app configures a connector. Never open remote access just for easier testing when unit tests can use `MBeanServer.addNotificationListener` in-process.

### 18.2. JMX RMI connectors require dedicated infrastructure setup

Illustrative remote URL:

~~~text
service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi
~~~

RMI may use separate registry and endpoint ports; in containers, configure `java.rmi.server.hostname`, firewalls, and NAT correctly. Require TLS/certificates, authentication, and network allowlists. Never copy lab settings with TLS/auth disabled into production.

### 18.3. Serializable userData and classpath

Over remote JMX, a Notification containing `userData` can pass through Java serialization. If `userData` is a `QueueAlarm` record, the client must have the matching class/version and deserialize only trusted sources. For polyglot monitoring clients, primitives/simple maps, OpenType/`CompositeData`, or a JSON string with a public contract are much easier to interoperate with.

### 18.4. Permissions: read vs. invoke

Remote JMX clients can read MBeans, receive notifications, or invoke operations depending on principal and connector policy. An application using JMX notifications solely for monitoring should never grant arbitrary remote invoke/write access. Least privilege on the JMX server remains necessary even when the Spring Integration flow validates payloads.

### 18.5. Do not treat a remote connector as a durable relay

If a client disconnects and reconnects, notifications emitted while offline may be lost. JMX does not have Kafka offsets or replay. If the client needs to know "what alerts happened while disconnected?", it must reconcile against a durable audit/metrics API, or the app must actively re-publish a contracted current-state snapshot.

## 19. Bridging HTTP/JMS/Kafka/DB to JMX notifications

In the **SPRING_INTEGRATION_ADAPTERS** module, the JMX publishing adapter can serve as an **observability fan-out branch**.

~~~mermaid
flowchart LR
    HTTP["HTTP inbound"]
    JMS["JMS / AMQP inbound"]
    KAFKA["Kafka inbound"]
    DATABASE["DB polling / CDC"]
    ROUTER["Spring Integration flow<br/>validate + route"]
    OUTBOX[("Business state + outbox")]
    PUB["JMX publishing channel"]
    JMX["JMX MBeanServer / JConsole"]
    HTTP --> ROUTER
    JMS --> ROUTER
    KAFKA --> ROUTER
    DATABASE --> ROUTER
    ROUTER --> OUTBOX
    ROUTER --> PUB --> JMX
~~~

### 19.1. Where to place the adapter in the flow?

**Do not** emit a JMX `CRITICAL` notification before the business transaction commits if the type means "order failure has been recorded." Clarify event semantics: `attempted`, `rejected`, `committed`, or `failed`? When alignment with the DB is required, publish after commit or from an outbox relay.

### 19.2. How do exceptions on the JMX side branch affect the business flow?

On a synchronous `DirectChannel` branch, a failing JMX handler throws its exception back upstream. If JMX is strictly optional monitoring, **isolate the JMX publishing path** from the main transaction using an async channel, error flow, or outbox. If JMX is a critical boundary, define a deliberate fail-fast policy rather than assuming "JMX is just monitoring so swallow all errors" and losing visibility.

### 19.3. Forwarding back to JMS/Kafka can create loops

A JMX inbound listener could forward notifications to a Kafka topic, whose consumer then re-emits them to JMX. Design explicit routes, event origins, hop metadata, and deduplication; never use `ObjectName` or `JmxHeaders.NOTIFICATION_TYPE` alone as a unique business event ID.

### 19.4. Distinguish event publication from state snapshots

JMX notifications report "a change or alert occurred"; JMX attribute/tree polling reports "the current state." An application can provide **both** so consumers see transitions while online and read current state upon reconnecting. Still, a current-state read cannot reconstruct all missed history.

## 20. Observability: what should you measure on the publisher?

| Suggested metric/field | Purpose |
| --- | --- |
| `jmx_publication_attempts_total` | Number of Spring messages attempted for publication. |
| `jmx_publication_success_total{type}` | Successful publications by type. |
| `jmx_publication_errors_total{kind}` | Mapping, registration, and JMX publish errors. |
| `jmx_publisher_mbean_registered` | Whether the `ObjectName` exists in `MBeanServer`. |
| `jmx_publication_duration_seconds` | Handler/publishing processing time. |
| `jmx_publication_payload_bytes` | Serialized size of text/`userData` if measured. |
| `jmx_publication_type_invalid_total` | Messages rejected for invalid type/schema. |
| `jmx_publication_filtered_total{reason}` | Messages dropped before the handler per policy. |
| `jmx_outbound_channel_backlog` | Queue depth when using async/buffering. |
| `jmx_remote_client_connectivity` | Connector/client status if an observation hook exists. |
| `jmx_alert_state_transitions_total` | Counts severity transitions rather than every sample. |
| `outbox_pending_alarm_count` | Durable alarms awaiting relay, if using an outbox. |

These metric names are **design suggestions**, not exact names automatically emitted by Spring Integration out of the box. When enabling Spring Integration management/Micrometer, check exact metric names for your version rather than assuming they exist unconfigured.

### 20.1. Do not use eventId as a metric label

`eventId`, JMX notification sequences, and `ObjectName`s with many instance names create very high cardinality. Use bounded type/severity/service-group labels; keep detailed event IDs in access-controlled structured logs and traces.

### 20.2. Logging a publication accurately

~~~text
eventId=evt-001
springChannel=jmx.notifications.out
notificationType=demo.queue.depth.critical
publisherObjectName=demo.integration:type=AlarmPublisher,name=Orders
result=JMX_PUBLISH_INVOKED
businessDeliveryAck=NOT_APPLICABLE
~~~

Never log `DELIVERED_TO_ALL_LISTENERS=true` without a dedicated observation/ACK mechanism. A disconnected listener may never have seen the publication.

### 20.3. Alert when the publisher ObjectName disappears

Maintain a health check using `MBeanServer.isRegistered(publisherObjectName)` alongside handler error metrics. Still, `isRegistered=true` does not guarantee remote clients are subscribed or able to decode the `userData` schema.


## 21. Troubleshooting across each point in the pipeline

| Symptom | Possible cause | Verification step |
| --- | --- | --- |
| Context fails to start with publisher | Missing `MBeanExporter`. | Enable `@EnableMBeanExport` or `<context:mbean-export/>`. |
| Duplicate `ObjectName` | Two handlers/MBeans share the registry name. | Assign a unique owner and `ObjectName`. |
| Publisher missing in JConsole | Wrong `MBeanServer` selected, or exporter did not register it. | Check `MBeanServer.isRegistered(ObjectName)`. |
| Publisher exists but no notifications arrive | No Spring Message sent, no listener attached, or wrong route. | Send a test message and attach a local `addNotificationListener`. |
| Notification type is default instead of header | Wrong header key or header stripped in flow. | Use `JmxHeaders.NOTIFICATION_TYPE`. |
| No valid notification type | Missing both header and default type. | Add fallback or type header. |
| Text is not in `userData` | Default mapper places `String` into `getMessage()`. | Read message text or use a custom mapper. |
| Record does not appear in `getMessage()` | Default mapper places non-String into `getUserData()`. | Check DTO and remote class availability. |
| Remote consumer cannot decode record | Classpath or Java serialization mismatch. | Use an interoperable DTO, OpenType, or JSON. |
| Adapter fails after hot reload | Stale exporter, handler delegate, or registration. | Verify MBean ownership and context lifecycle. |
| Duplicate notifications sent | Duplicate routes, resent events, or multiple publishers. | Check `eventId`, topology, and dedup policy. |
| Notifications arrive slowly | `DirectChannel` blocking, slow JMX client, or saturated queue. | Measure latency, use bounded async and sampling. |
| Remote JMX fails to connect | TLS/auth/firewall/RMI hostname or port issue. | Check connector config; never disable security. |
| CI fails with `InstanceAlreadyExistsException` | Multiple test contexts share platform server and `ObjectName`. | Use distinct test names, cleanup, or serial tests. |
| Notifications missed while client offline | JMX has no replay. | Use durable audit/outbox and current-state reads. |
| Java imports fail on Integration 7.x | Handler moved to `jmx.outbound`. | Check Javadocs for your exact dependency version. |

### 21.1. Check the JMX registry first

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName publisherName = new ObjectName(
        "demo.integration:type=AlarmPublisher,name=Orders");

System.out.println("Publisher registered: "
        + server.isRegistered(publisherName));
~~~

If this returns `false`, check `MBeanExporter`, `ObjectName`, native handler initialization, and the Spring context. If `true` yet no notifications arrive, attach a `NotificationListener` via the JMX API on the **exact same server**, send a test message to `jmx.notifications.out`, and verify `type` and `payload`.

### 21.2. Use the right header

`JmxHeaders.NOTIFICATION_TYPE` is the notification classification key. Do not confuse it with Spring `contentType`/`MessageHeaders.ID`, and do not confuse `Notification.getType()` with a Java DTO class name.

### 21.3. Do not log "sent" on every branch

An exception in the JMX mapper/handler or a `DirectChannel` with no consumer needs dedicated metrics. Even when the Spring channel accepts the message, log `JMX_PUBLISH_INVOKED` rather than concluding `DELIVERED_TO_EVERY_LISTENER` without business acknowledgement.

## 22. Anti-patterns and fixes

| Anti-pattern | Why it is wrong | Correct approach |
| --- | --- | --- |
| Using notification-publishing as an inbound listener. | Wrong data direction. | Outbound publisher receives Spring messages; inbound listener receives JMX Notifications. |
| Omitting `MBeanExporter`. | Publisher delegate cannot be exported or receive `NotificationPublisher`. | Add `@EnableMBeanExport` or `<context:mbean-export/>`. |
| Adding a poller to an outbound publisher. | Arriving messages on the channel already trigger the handler. | Pollers are for sources that require polling. |
| Assigning two handlers the same `ObjectName`. | MBean registration collision. | One publisher, multiple notification types via header. |
| Setting `contentType` instead of `JmxHeaders.NOTIFICATION_TYPE`. | The two headers have different contracts. | Use the proper JMX header or fallback default type. |
| Assuming a `String` ends up in `userData`. | Default mapper puts `String` in notification `message`. | Read `getMessage()` or use a custom mapper. |
| Pushing full JPA entities/Exceptions into `userData`. | Serialization, memory, secret-leak, and schema risks. | Small, redacted, versioned DTOs. |
| Using `sequenceNumber` as business `eventId`. | Sequence resets per publisher instance. | Business ID durable across retries/restarts. |
| Treating `send(true)` as an ACK from all remote listeners. | JMX has no business ACK. | Separate business ACK / durable protocol. |
| Sending every gauge sample as a `CRITICAL` event. | Alert storm while value stays flat. | State transitions, hysteresis, and cooldown. |
| Public JMX/RMI without TLS/auth. | Exposes JVM management privileges. | Enforce TLS, authentication, and firewalling. |
| Treating in-memory `ExecutorChannel` as durable. | Unpersisted messages are lost on crash. | Durable inbox/outbox. |
| Assuming remote clients naturally know the publisher's Java record. | May lack the class or serializer. | OpenType, primitives, or JSON contract. |
| Using JMX as Kafka across data centers. | No retention, offsets, or replay. | Durable broker for business events; JMX for monitoring. |
| Swallowing exceptions and marking published. | Hides failures. | Error path, metrics, and backlog/reconciliation checks. |

## 23. Quality-standard test matrix

An application using the native publisher should cover at least these test groups:

| Case | Expectation |
| --- | --- |
| Spring context with exporter | Publisher `ObjectName` is registered. |
| Spring context missing exporter | Startup fails with a clear cause. |
| Two publishers with duplicate `ObjectName` | Collision handled; no silent overwrite. |
| String payload and default type | `getMessage()` and `getType()` match. |
| String payload with header override | Header overrides default. |
| Non-String payload | `getUserData()` contains the expected DTO. |
| Invalid input type/header | Rejected before publisher, recorded in metrics/error path. |
| Custom `OutboundMessageMapper` | Type/source/time/sequence/userData match mapper. |
| Listener filter | Receives only matching notification types. |
| Late-attaching subscriber | Previously published notifications are not replayed. |
| Listener removed | Stops receiving; avoids callback leaks. |
| Multiple listeners | Separate filters and clear listener ownership. |
| Hot reload / restart | No stale MBean registrations left behind. |
| `DirectChannel` handler failure | Caller observes exception per channel contract. |
| `ExecutorChannel` handler failure | Error monitoring is not lost. |
| Warning flood | Coalescing, bounded queue, and lag metrics work. |
| Remote class mismatch | Detects `userData` serialization incompatibility. |
| Remote TLS/auth | Unauthenticated clients are rejected. |
| Remote disconnect/reconnect | Does not claim automatic replay. |
| Bridge loop | Does not republish notifications infinitely. |
| Outbox retry | Stable `eventId` and downstream idempotency. |

### 23.1. Test JMX directly without bypassing the Spring flow

You can test `NotificationPublisherAware` standalone with a Spring MBean, yet that does not prove `NotificationPublishingMessageHandler` is wired to the input channel. A full integration test should cover **Spring MessageChannel → handler → MBeanServer → NotificationListener**, as in section 10.

### 23.2. Run remote fault injection in a lab, never on a production JVM

Scenarios like network partitions, remote connector restarts, and certificate expiration must be tested in an isolated environment with fake credentials so real operators are unaffected. After reconnecting, reconcile against the durable alarm log if required by the business.

## 24. Hands-on exercise: managing alerts with JMX

**Scenario:** A service ingests metrics via JMS/Kafka, computes severity for the `Orders` queue, writes to a database, and emits JMX notifications to JConsole or a JMX listener service.

### 24.1. Requirements

1. Add `spring-integration-jmx` aligned with the Spring Boot BOM.
2. Create an output `MessageChannel` named `jmx.notifications.out`.
3. Configure a native XML `notification-publishing-channel-adapter` with `ObjectName` `demo.integration:type=AlarmPublisher,name=Orders`.
4. Enable `<context:mbean-export/>` and explain why omitting the exporter fails.
5. Build the Java equivalent with `@EnableMBeanExport` and `NotificationPublishingMessageHandler`; run **one or the other** to avoid `ObjectName` collisions.
6. Send a `String` payload without a type header; inspect fallback type and `getMessage()`.
7. Send a `String` payload with `JmxHeaders.NOTIFICATION_TYPE`; verify the header overrides the default.
8. Send a `QueueAlarm` record as payload; inspect `Notification.getUserData()`.
9. Define warning/critical/recovered types following the dot-delimited convention.
10. Register a local `NotificationListener` via `MBeanServer.addNotificationListener` and wait with `BlockingQueue.poll(timeout)`.
11. Check `isRegistered(publisherName)` before sending and clean up the listener after tests.
12. Create a custom `OutboundMessageMapper<Notification>` to replace the default handler.
13. Separate business `eventId`/`occurredAt` from JMX sequence/time.
14. Design hysteresis/cooldown so `CRITICAL` is not published on every gauge sample.
15. Simulate a slow JMX handler and compare `DirectChannel` vs. bounded `ExecutorChannel`.
16. Write tests for missing exporter, invalid type, `ObjectName` collision, and `userData` incompatible with remote clients.
17. Attach a listener after emitting an event and explain why no replay occurs.
18. Write alarm events to a durable audit/outbox when the business cannot tolerate data loss.
19. Provide a durable JMS/AMQP/Kafka branch for business alerts alongside the JMX branch for monitoring.
20. Prevent feedback loops if an inbound JMX listener publishes messages back into the same outbound channel.
21. Configure a remote JMX lab with TLS/auth/firewall and a least-privilege principal.
22. Instrument attempt/success/error metrics, publisher `ObjectName` registration, and outbox backlog.

### 24.2. Acceptance criteria

- Native outbound publisher has a valid `ObjectName` and registered `MBeanExporter`.
- Spring Messages sent to the channel produce JMX Notifications without a poller.
- The mapper properly separates String vs. non-String payloads and follows type header precedence.
- JUnit local listener actually observes notifications and cleans up registrations.
- Error handling, backpressure, and remote security are covered.
- Clearly states that channel `send` is not an ACK from all listeners.
- Uses a durable audit/outbox when the business requires retention guarantees.

### 24.3. Advanced exercise: unifying multi-source alerts

HTTP inbound receives incidents, JMS consumer receives queue failures, and Kafka listener receives throughput alarms. Normalize them into an `InfrastructureAlarm(eventId, sourceNode, severity, occurredAt, details)` DTO; route to both a JMX publishing branch and a durable branch. Use `origin`/hop metadata to prevent event loops, and the same business ID for downstream idempotency.

## 25. Self-check questions

1. Is the notification-publishing adapter inbound or outbound?
2. Does it receive Spring messages or JMX callbacks?
3. What is the native Java publisher class?
4. What is the role of `MBeanExporter`?
5. How does `MBeanServer` differ from `MBeanExporter`?
6. What is `PublisherDelegate` used for?
7. Is the publisher `ObjectName` the same as the Spring channel ID?
8. At which stage does a missing `MBeanExporter` cause an error?
9. Which XML element is equivalent to `@EnableMBeanExport`?
10. Which header determines the JMX notification type?
11. When both the header and `default-notification-type` are present, which takes precedence?
12. Why should notification types be dot-delimited?
13. Which field does a String payload map to by default?
14. Which field does a non-String payload map to by default?
15. Is `userData` always suitable for remote deserialization?
16. What risk does a Java record in `userData` pose when a remote client lacks the class?
17. Can `sequenceNumber` replace a business event ID?
18. Is `Notification` `timeStamp` always the business `occurredAt`?
19. Does a custom mapper automatically use the handler's `default-notification-type`?
20. Why shouldn't two publishers share the same `ObjectName` on one server?
21. Does `MessageChannel.send(true)` mean clients have ACKed?
22. Can a listener attached after an event is emitted receive it retroactively?
23. Does the publisher or the listener register `NotificationFilter`?
24. How do `handback` and `userData` differ?
25. Why shouldn't JMX be used for durable messaging between JVMs?
26. What problem arises if a polling flow emits `CRITICAL` every 5 seconds?
27. How does hysteresis differ from a simple threshold predicate?
28. How does `DirectChannel` with a slow handler affect upstream callers?
29. Does `ExecutorChannel` turn JMX into a durable broker?
30. Which security layers does remote JMX require?
31. Which boundary does a `MBeanServer.addNotificationListener` test prove?
32. Into which package does Spring Integration 7.x move the handler import?
33. Why should type and schema be validated before publishing?
34. How do you prevent a bridge loop between publisher and listener?
35. If alarms must be preserved while JMX clients are offline, what should you use?

**Hint:** Focus on three questions: **what triggers the outbound handler**, **how type and payload map**, and **whether listeners are actually guaranteed to receive the message**.

## 26. Conclusion and references

The **JMX notification-publishing adapter** lets Spring Integration emit JVM management events:

- Native XML `int-jmx:notification-publishing-channel-adapter` or Java `NotificationPublishingMessageHandler`.
- Requires `MBeanExporter` to register `PublisherDelegate` and provide `NotificationPublisher`, via `<context:mbean-export/>` or `@EnableMBeanExport`.
- `object-name` is the JMX publisher name; `channel` is the Spring input channel.
- Default mapper maps **String payload → notification message text** and **non-String payload → userData**.
- `JmxHeaders.NOTIFICATION_TYPE` overrides `default-notification-type`; a custom mapper is responsible for its own type/schema.
- Spring channel send / JMX publish carries no business ACK from listeners, nor retention/replay.
- Remote JMX requires TLS/auth/ACLs/firewalls, and `userData` must follow a compatible serialization contract.
- Protect the application with filtering, rate limiting, error handling, MBean registration health checks, and a durable outbox when SLAs require it.

In **SPRING_INTEGRATION_ADAPTERS**, the pipeline **HTTP/JMS/AMQP/Kafka/DB → MessageChannel → JMX publishing handler → MBeanServer → monitoring clients** brings visibility into JVM activity. JMX notifications suit real-time monitoring for directly subscribed listeners; when replay and business commit guarantees are needed, use a dedicated store or broker.

### 26.1. Technical sources for API verification

- [Spring Integration Reference – JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html): native XML adapter, `MBeanExporter`, payload type mapping, and notification type precedence.
- [NotificationPublishingMessageHandler 6.4 Javadoc](https://www.springframework.org/spring-integration/docs/6.4.1/api/org/springframework/integration/jmx/NotificationPublishingMessageHandler.html): constructors and setters.
- [NotificationPublishingMessageHandler 7.x Javadoc](https://www.springframework.org/spring-integration/docs/current/api/org/springframework/integration/jmx/outbound/NotificationPublishingMessageHandler.html): `jmx.outbound` package.
- [EnableMBeanExport – Spring Framework](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html): Java export config equivalent to XML.
- [Spring Framework JMX Publishing Notifications](https://docs.spring.io/spring-framework/docs/5.3.x/reference/html/integration.html): `NotificationPublisherAware` and `NotificationPublisher`.
- [Java JMX API 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/package-summary.html): `MBeanServer`/`NotificationListener`/`ObjectName`.

**STEP 4 scope:** This Knowledge article contains explanations, Java/XML examples, and tests for learning. For real projects, verify dependency versions, build, and run integration tests. Technical Content QA/refactoring belongs to **STEP 6**, not the STEP 4 authoring task.




