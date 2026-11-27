# JMX notification-listening adapter

## 1. Problem: receiving JMX management events into an IntegrationFlow

A Java application has an MBean that monitors queue depth, connection pool state, or resource alerts. When the queue exceeds a threshold, the MBean emits a **JMX Notification**. The backend wants to route this notification immediately into Spring Integration to:

- Inspect the event type and emission source;
- Transform it into an explicit message contract;
- Record audit/metrics, trigger alerts, or forward to HTTP/JMS/AMQP/Kafka;
- Avoid running a scheduled job to poll MBean attributes repeatedly;
- Manage listener registration and unregistration alongside the Spring application lifecycle.

Spring Integration provides the **JMX notification-listening channel adapter** to bridge **JMX Notification → Spring Message → MessageChannel**. The adapter registers a `NotificationListener` with the `MBeanServer`, waits for notifications to occur, and places the `javax.management.Notification` object itself into the Spring message payload. It is an **inbound, event-driven adapter**, not an attribute poller.

The lesson **“JMX notification-listening adapter”** belongs to the **Adapter JMX** chapter, **SPRING_INTEGRATION_ADAPTERS** module. This module focuses on connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing file, SFTP, HTTP, JMS, AMQP, Kafka, and database exchanges, message contract handling, error handling, and connection lifecycles. JMX is a classic example of an event source inside or alongside the JVM that needs to be brought into the same integration pipeline.

After this lesson, the reader will be able to:

1. Distinguish JMX `MBean`, `MBeanServer`, `ObjectName`, `Notification`, `NotificationBroadcaster`, and `NotificationListener`.
2. Explain accurately how the notification-listening adapter works and why **no poller is needed**.
3. Configure `notification-listening-channel-adapter` using the Spring Integration XML namespace.
4. Create a `NotificationListeningMessageProducer` Java bean to connect JMX to a Spring `DirectChannel` and `IntegrationFlow`.
5. Write an MBean that emits notifications, filter by notification type, use an optional handback, and normalize messages.
6. Distinguish an exact object name from an `ObjectName` pattern, paying attention to dynamic MBean registration and lifecycle.
7. Evaluate backpressure, threading, error propagation, remote JMX security, and durability limits of JMX notifications.
8. Write JUnit tests with an in-process MBeanServer to test filtering, handlers, stop/start, and failure scenarios.
9. Decide when to use a notification listener, attribute polling, an outbound gateway, or a durable messaging broker.

**Key takeaway:** JMX notifications detect management events **as they happen**; they are not a topic broker, do not provide QoS/retained subscriptions like MQTT, and do not provide durable replay or business-level acknowledgement by default.

## 2. JMX Notification → Spring Integration architecture

~~~mermaid
flowchart LR
    M["Managed component<br/>QueueHealth MBean"]
    S[("MBeanServer")]
    L["NotificationListeningMessageProducer<br/>JMX NotificationListener"]
    CH["jmx.notifications.in<br/>MessageChannel"]
    F["IntegrationFlow<br/>validate + transform + route"]
    A[("Audit / Metrics")]
    Q["Kafka / JMS / AMQP / HTTP"]
    M -->|"sendNotification"| S
    S -->|"JMX listener callback"| L
    L -->|"Message<Notification>"| CH
    CH --> F
    F --> A
    F --> Q
~~~

**Processing flow from source to destination:**

1. The managed component creates a `Notification`, for example with type `demo.queue.depth.changed`.
2. A `NotificationBroadcaster` MBean sends the notification to registered listeners.
3. `NotificationListeningMessageProducer` holds an `ObjectName` locating the MBean and registers the listener via `MBeanServer`.
4. When the callback runs, the producer creates a Spring message containing the **JMX Notification object** as its payload and sends it to the output channel.
5. The Spring Integration flow reads the `type`, `source`, `sequenceNumber`, `timeStamp`, `message`, and `userData` fields, validates the contract, and converts it to a business DTO.
6. Downstream handlers write logs/audit records or perform outbound integration according to their own policies.

The goal is to **bring notifications into the message pipeline**, not to make JMX directly responsible for queuing, transactions, or message retention.

### 2.1. Comparison with other adapters

| Endpoint type | Trigger | Main payload | When to use? |
| --- | --- | --- | --- |
| JMX notification-listening inbound | JMX `NotificationListener` callback | `Notification` | Capture changes/events proactively emitted by an MBean. |
| JMX attribute-polling inbound | Scheduled Spring poller | MBean attribute value | The MBean only exposes attributes that need periodic reading. |
| JMX tree-polling inbound | Poller taking an MBean tree snapshot | MBean/attribute structure | Inventory/monitoring of an entire group of MBeans. |
| JMX operation-invoking outbound gateway | Spring message invoking an MBean operation | Operation call result | Control/management commands requiring request-reply. |
| MQTT inbound adapter | Broker delivers PUBLISH per subscription | Converted payload | Receiving events from MQTT devices/brokers. |
| JMS/AMQP/Kafka consumers | Broker/log delivers messages | Domain record/message | Need queues/streams and broker-level retry/replay/durability. |

JMX listeners typically serve monitoring **within the JVM or from a configured MBeanServerConnection**. They do not replace database Change Data Capture or a dedicated message broker system.

## 3. JMX fundamentals: object types to distinguish

### 3.1. MBean and MBeanServer

An **MBean** is a managed bean that the JMX runtime can discover and interact with through an `MBeanServer`. An MBean has attributes, operations, and can emit notifications. A **Standard MBean** typically has an interface named `XxxMBean` and a class `Xxx` implementing that interface.

`MBeanServer` is JMX's registry and dispatch infrastructure inside the JVM. You can use the platform server:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
~~~

`ManagementFactory.getPlatformMBeanServer()` is not synonymous with an MQTT broker or a Spring channel. It is the JVM's JMX management endpoint, accessible from Java code and via a remote connector **if explicitly configured**.

### 3.2. ObjectName

JMX uses `javax.management.ObjectName` to identify MBeans:

~~~text
demo.integration:type=QueueHealth,name=Orders
java.lang:type=Memory
java.lang:type=GarbageCollector,name=G1 Young Generation
~~~

An ObjectName has a domain before the `:` character, followed by a list of key/value properties. For the demo:

~~~java
import javax.management.ObjectName;

ObjectName objectName =
        new ObjectName("demo.integration:type=QueueHealth,name=Orders");
~~~

Do not treat this as a filesystem path, Kafka topic, or Spring bean name. ObjectName has its own quoting/wildcard rules; avoid concatenating untrusted values from an HTTP caller directly into an ObjectName without validating or quoting them first.

### 3.3. Notification

A JMX `Notification` includes commonly used metadata:

| API | Meaning | Points to note |
| --- | --- | --- |
| `getType()` | Event type, typically using a hierarchical name like `demo.queue.depth.changed`. | Does not guarantee trust or payload schema by itself. |
| `getSource()` | Notification source according to the MBean/provider. | Not always a `String`/`ObjectName` as expected by the application. |
| `getSequenceNumber()` | Sequence number managed by the publisher. | Not a globally unique event ID; may reset on restart. |
| `getTimeStamp()` | Notification timestamp. | Depends on the source clock; do not rely on it for strict ordering across MBeans. |
| `getMessage()` | Text description. | Do not parse free-form text as the primary schema. |
| `getUserData()` | Application-specific data. | Type `Object`; validate before casting or serializing. |

Example of creating a notification:

~~~java
import javax.management.Notification;

Notification notification = new Notification(
        "demo.queue.depth.changed",
        sourceObject,
        42L,
        System.currentTimeMillis(),
        "Orders queue depth changed");

notification.setUserData(Integer.valueOf(25));
~~~

**Notification type is not a Java class name.** You should define stable type names and version `userData` if consumers need long-term processing compatibility.

### 3.4. NotificationBroadcaster and NotificationListener

An MBean that emits notifications typically implements `NotificationBroadcaster` or extends `NotificationBroadcasterSupport`. A subscriber implements `NotificationListener` with the method:

~~~java
void handleNotification(
        Notification notification,
        Object handback);
~~~

`handback` is context specified by the **listener subscriber**; JMX passes this context back when invoking the callback. It is not automatically `Notification.getUserData()`.

### 3.5. NotificationFilter

`NotificationFilter` decides which notifications are forwarded to the listener:

~~~java
import javax.management.NotificationFilter;

NotificationFilter onlyQueueDepth =
        notification -> "demo.queue.depth.changed"
                .equals(notification.getType());
~~~

A filter is a **selection layer for notification type/metadata** right at listener registration. It is **not** authorization; the MBean source and JMX connection still need to be trusted and authorized.

## 4. How the notification-listening channel adapter works

From Spring Integration's perspective, the adapter needs:

1. An `MBeanServer` or `MBeanServerConnection` to register the listener;
2. One or more `ObjectName`s of MBeans emitting notifications;
3. A `MessageChannel` as output;
4. An optional `NotificationFilter` to discard unwanted events;
5. An optional **handback** context.

The adapter registers when the endpoint starts and unregisters when it stops. Typically Spring manages the endpoint via `SmartLifecycle`. In scenarios where an MBean is exported into the context late, the implementation also handles lifecycle/context refreshed events to register the listener once the MBean is ready; test this in practice alongside your `MBeanExporter` configuration.

### 4.1. Event-driven, not polling

~~~text
MBean sends JMX Notification
         ↓
NotificationListener callback
         ↓
Spring Integration MessageChannel
~~~

You do not need `@Poller` or `<int:poller>` on a notification-listening adapter. Adding a poller to the endpoint is not how you make callbacks arrive faster.

Only when **internal downstream** processing moves to a `QueueChannel` might a poller/consumer be needed to drain messages from that queue; this is independent of the JMX subscription mechanism.

### 4.2. Payload and headers

Spring Integration's `NotificationListeningMessageProducer` emits a Spring message whose **payload is the `Notification` object itself**. For a non-null handback, the adapter puts the handback into a JMX-related header (see `JmxHeaders.NOTIFICATION_HANDBACK` in the corresponding API).

Before sending to Kafka/HTTP/JSON, you should **transform the Notification into a DTO** with stable fields. Do not pass raw `Notification.getSource()` or `userData` directly to a remote transport without a converter, schema, or trust policy.

### 4.3. No message-broker-style ACK or replay

Standard JMX notifications do not natively provide:

- Durable disk-backed subscription backlogs;
- MQTT QoS 1/2, `PUBACK`, or retained messages;
- JMS transaction/ack modes;
- Kafka offsets and replay;
- Automatic dead-letter queues;
- System-wide unique event IDs.

If a consumer is slow/offline or the process crashes, **JMX Notifications can be missed**. When storage guarantees are required, persist to a database/inbox or forward events to an appropriate message broker, and design idempotency/recovery in the application.

## 5. XML namespace: minimal configuration

Spring Integration provides the `int-jmx` namespace and element:

~~~xml
<int-jmx:notification-listening-channel-adapter
    id="queueNotificationListener"
    channel="jmxNotifications"
    object-name="demo.integration:type=QueueHealth,name=Orders"/>
~~~

By default, the adapter looks for an MBeanServer bean named `mbeanServer`. In Spring XML, `<context:mbean-server/>` usually creates a bean with the matching name; to use a different server, set the `mbean-server` attribute.

Abbreviated XML context example:

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

    <int:channel id="jmxNotifications"/>

    <int-jmx:notification-listening-channel-adapter
        id="queueNotificationListener"
        mbean-server="mbeanServer"
        channel="jmxNotifications"
        object-name="demo.integration:type=QueueHealth,name=Orders"/>
</beans>
~~~

This snippet creates the server, channel, and adapter, **but does not create the publisher MBean yet**. An MBean matching the `ObjectName` must already be registered on the **same** server; otherwise, the adapter has no event source to listen to. The Java section in section 10 will create the publisher MBean.

### 5.1. NotificationFilter and handback in XML

The adapter supports referencing a `NotificationFilter` and a handback object:

~~~xml
<int-jmx:notification-listening-channel-adapter
    id="queueNotificationListener"
    channel="jmxNotifications"
    mbean-server="mbeanServer"
    object-name="demo.integration:type=QueueHealth,name=Orders"
    notification-filter="queueDepthFilter"
    handback="queueListenerContext"/>
~~~

Here, `queueDepthFilter` and `queueListenerContext` are **bean references that must be defined** in the context. This snippet replaces the minimal adapter in the previous section; do not create two adapters with the same name. The names and semantics of both attributes are defined in the JMX namespace; filtering at callback time does not replace schema validation, authorization, or downstream error handling.

### 5.2. Bean identifiers and JMX objects are two separate namespaces

~~~text
Spring adapter bean ID:  queueNotificationListener
Spring channel ID:       jmxNotifications
JMX ObjectName:          demo.integration:type=QueueHealth,name=Orders
Spring MBeanServer bean: mbeanServer
~~~

Changing the channel `id` does not change the `ObjectName` in the JMX server; changing the `ObjectName` can cause the adapter to register against the wrong MBean or receive no events even though the Spring channel is still working.

## 6. Listening to multiple MBeans with an ObjectName pattern

With multiple MBeans:

~~~text
demo.integration:type=QueueHealth,name=Orders
demo.integration:type=QueueHealth,name=Billing
demo.integration:type=QueueHealth,name=Notifications
~~~

You can use a pattern:

~~~xml
<int-jmx:notification-listening-channel-adapter
    id="allQueueNotifications"
    channel="jmxNotifications"
    object-name="demo.integration:type=QueueHealth,name=*"/>
~~~

This is a capability **specific to the notification-listening adapter**: an ObjectName pattern can register listeners for MBeans matching the pattern. You can also use a SpEL list of multiple names/patterns in the XML namespace in supported versions.

### 6.1. A pattern does not mean tracking new MBeans automatically forever

The critical point is **when listeners are resolved and registered**. An adapter can find the matching MBeans at startup/refresh, but you **should not assume** it automatically registers with every MBean added later at runtime without a refresh mechanism. If MBeans are dynamically created and destroyed frequently, test the behavior specifically on your Spring Integration version, manage re-registration, or consider listening to `MBeanServerDelegate` for registry changes if truly needed.

### 6.2. Broad patterns easily generate load and expose metadata

A `demo.integration:*` filter or overly broad pattern can pull in hundreds of MBeans emitting notifications with varying types/payloads. Restrict the domain/type and use a dedicated NotificationFilter and flow routing. Nor should pattern matching be treated as proof that the application is authorized to manage every remote MBean.

### 6.3. One adapter or multiple adapters?

| Requirement | Recommendation |
| --- | --- |
| Multiple MBeans with the same schema/type and lifecycle | A pattern or list of object names in one adapter. |
| MBeans with different sources/privileges | Separate MBeanServerConnections/adapters by security boundaries. |
| Notifications with very different schemas | Route by type/source to separate flows. |
| Heavily skewed load across groups | Separate channels/queues and backpressure policies. |
| Independent operational control needed | Separate endpoints, metrics, and lifecycles. |

## 7. Notification payload contract: from JMX object to business event

A `Notification` is a generic object. If passed directly to an outbound HTTP gateway or Kafka producer, consumers may receive an unstable internal Java representation, or the serializer may fail on unsupported objects inside `source`/`userData`.

You should convert it to a DTO:

~~~java
public record QueueDepthEvent(
        String eventType,
        String sourceName,
        long sequenceNumber,
        long occurredAtEpochMillis,
        int depth) {
}
~~~

Example mapping:

~~~text
Notification.type                 -> eventType
Listener configuration / ObjectName -> sourceName
Notification.sequenceNumber       -> sequenceNumber
Notification.timeStamp            -> occurredAtEpochMillis
Notification.userData=Integer     -> depth
~~~

If using handback as source context, set a stable string/ID rather than referencing a service object in the Spring context. Notification `message` should only be used for logs/UI; do not regex-parse it as a business schema when `userData` already has an explicit contract.

### 7.1. Sequence is not a durable event ID

An MBean can emit `sequenceNumber=1,2,3,...` during the lifetime of an instance, then reset to 1 when the JVM restarts. Across multiple MBeans, the sequence is not a system-wide counter either. If idempotency is needed when saving to a database or publishing to Kafka, define an ID such as `(sourceId, sourceBootId, sequenceNumber)` or assign a dedicated `eventId` and manage collisions and retention.

### 7.2. Timestamp and source may not be trustworthy

Clocks can drift; remote MBeans do not necessarily share the exact same timezone or clock. `Notification.getSource()` can be an object, string, or ObjectName depending on the broadcaster. Therefore, logs should use a validated configuration ID and safe source metadata rather than blindly casting `getSource()` to `ObjectName` and assuming it is always valid.

### 7.3. Filtering by type does not replace business validation

Even when a filter only accepts `demo.queue.depth.changed`, `userData` may be null, of the wrong type, or negative. The flow must validate `type` and `userData` **before** constructing the DTO. For remote JMX or untrusted MBean extensions, do not deserialize unfamiliar object graphs or log raw userData indiscriminately.


## 8. Dependencies and distinguishing Spring Integration 6.x/7.x

The following examples use **Java 17+, Spring Boot, and Spring Integration 6.x** with the dedicated JMX module:

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

Use the Spring Boot BOM to keep versions aligned; do not arbitrarily mix major versions of Spring Boot, Spring Framework, and Spring Integration.

**Important note on Java imports:**

| Spring Integration | Notification listener producer class | Note |
| --- | --- | --- |
| 6.x (e.g. 6.4/6.5) | `org.springframework.integration.jmx.NotificationListeningMessageProducer` | The Java examples below use this import. |
| 7.x (e.g. 7.0/7.1) | `org.springframework.integration.jmx.inbound.NotificationListeningMessageProducer` | Package moved to `jmx.inbound`; adjust the import and verify compatibility. |

Across both product lines, the conceptual API still includes `setServer(...)`, `setObjectName(...)`, `setFilter(...)`, `setHandback(...)`, and the output channel. Do not assume that copying 6.x code and just bumping the dependency version will compile in 7.x without updating imports. Beyond package changes, verify the Java baseline, Spring Boot BOM, and any deprecated or moved APIs.

### 8.1. Why isn't adding spring-boot-starter-actuator enough?

Spring Boot Actuator has its own HTTP/management endpoints and can expose metrics/health, but it does not automatically turn a JMX Notification into a Spring Integration message. To use `notification-listening-channel-adapter`, you must have the **Spring Integration JMX module** and an MBean source emitting notifications.

### 8.2. Demo project

~~~text
src/main/java/demo/jmxnotifications/
    JmxNotificationsApplication.java
    QueueHealthMBean.java
    QueueHealth.java
    QueueDepthEvent.java
    NotificationSink.java
    JmxNotificationConfiguration.java

src/test/java/demo/jmxnotifications/
    JmxNotificationFlowTest.java
~~~

All source files share the `demo.jmxnotifications` package. In the example, `QueueHealthMBean` and `QueueHealth` are separate `public` types placed in matching Java filenames. DTO/sink/config can be package-private.

## 9. MBean emitting Notifications: Standard MBean design

### 9.1. QueueHealthMBean interface

~~~java
package demo.jmxnotifications;

public interface QueueHealthMBean {

    int getDepth();

    void setDepth(int newDepth);

    void emitHeartbeat();
}
~~~

By Standard MBean convention, the management interface `QueueHealthMBean` must be public and the `QueueHealth` class implements it. Exposing `setDepth` makes the lab easy to drive from JConsole/Java tests; **production should not expose public operations that can spoof health data** without proper security and a clear use case.

### 9.2. QueueHealth extends NotificationBroadcasterSupport

~~~java
package demo.jmxnotifications;

import java.util.concurrent.atomic.AtomicLong;

import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueHealth
        extends NotificationBroadcasterSupport
        implements QueueHealthMBean {

    public static final String DEPTH_CHANGED =
            "demo.queue.depth.changed";

    public static final String HEARTBEAT =
            "demo.queue.heartbeat";

    private final AtomicLong nextSequence = new AtomicLong();

    private volatile int depth;

    @Override
    public int getDepth() {
        return depth;
    }

    @Override
    public void setDepth(int newDepth) {
        if (newDepth < 0) {
            throw new IllegalArgumentException(
                    "Queue depth must not be negative");
        }

        depth = newDepth;

        var notification = new Notification(
                DEPTH_CHANGED,
                this,
                nextSequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Orders queue depth changed");

        notification.setUserData(Integer.valueOf(newDepth));
        sendNotification(notification);
    }

    @Override
    public void emitHeartbeat() {
        var notification = new Notification(
                HEARTBEAT,
                this,
                nextSequence.incrementAndGet(),
                System.currentTimeMillis(),
                "QueueHealth heartbeat");

        sendNotification(notification);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
                new MBeanNotificationInfo(
                        new String[] { DEPTH_CHANGED, HEARTBEAT },
                        Notification.class.getName(),
                        "QueueHealth notifications")
        };
    }
}
~~~

**Part-by-part explanation:**

- `NotificationBroadcasterSupport` provides listener registration and notification emission.
- `QueueHealthMBean` allows JMX to manage the Standard MBean's attributes and operations.
- `new Notification(type, source, sequence, timeStamp, message)` constructs the event, and `setUserData(...)` attaches the depth.
- `AtomicLong` ensures safe sequence increments when multiple threads emit events from the same MBean instance.
- `getNotificationInfo()` advertises the expected notification types for JMX tools and consumers to discover.
- `emitHeartbeat()` produces a different notification type for testing that `NotificationFilter` only accepts `DEPTH_CHANGED`.

**Thread safety:** `volatile int depth` makes the new value visible to readers, while `nextSequence.incrementAndGet()` keeps sequence numbers increasing. If two operations must emit notifications in strict order without racing between state updates and event emission, add a lock or dedicated event loop; the demo focuses solely on the listener.

### 9.3. NotificationBroadcaster is not a durable queue

`sendNotification(notification)` dispatches to JMX listeners registered at that point in time. If the adapter has not started yet, or is not registered under the right ObjectName, the notification will not enter the Spring flow. There is no automatic offline backlog for a listener that does not yet exist.

### 9.4. Type schema and userData

In the demo, only `DEPTH_CHANGED` has an `Integer` userData. Heartbeat has no userData; if the flow attempts to cast every notification to `Integer` without checking the type, the handler will fail. Therefore, both filtering at the adapter and validating type/data in the flow are necessary.

## 10. Spring Java configuration: MBeanServer, MBeanExporter, and listener producer

Complete configuration example in `JmxNotificationConfiguration.java`:

~~~java
package demo.jmxnotifications;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationFilter;
import javax.management.ObjectName;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jmx.JmxHeaders;
import org.springframework.integration.jmx.NotificationListeningMessageProducer;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class JmxNotificationConfiguration {

    private static final String QUEUE_OBJECT_NAME =
            "demo.integration:type=QueueHealth,name=Orders";

    @Bean(name = "mbeanServer")
    MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    QueueHealth queueHealth() {
        return new QueueHealth();
    }

    @Bean
    MBeanExporter queueHealthExporter(
            MBeanServer mbeanServer,
            QueueHealth queueHealth) {

        var exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setBeans(Map.of(
                QUEUE_OBJECT_NAME, queueHealth));
        return exporter;
    }

    @Bean(name = "jmx.notifications.in")
    MessageChannel jmxNotificationsInput() {
        return new DirectChannel();
    }

    @Bean
    NotificationFilter queueDepthFilter() {
        return notification ->
                QueueHealth.DEPTH_CHANGED
                        .equals(notification.getType());
    }

    @Bean
    NotificationListeningMessageProducer queueNotificationAdapter(
            MBeanServer mbeanServer,
            NotificationFilter queueDepthFilter,
            @Qualifier("jmx.notifications.in")
            MessageChannel output) throws Exception {

        var adapter = new NotificationListeningMessageProducer();

        adapter.setServer(mbeanServer);
        adapter.setObjectName(new ObjectName(QUEUE_OBJECT_NAME));
        adapter.setFilter(queueDepthFilter);
        adapter.setHandback("orders-queue");
        adapter.setOutputChannel(output);

        return adapter;
    }

    @Bean
    NotificationSink notificationSink() {
        return new NotificationSink();
    }

    @Bean
    IntegrationFlow queueNotificationFlow(NotificationSink sink) {
        return IntegrationFlow.from("jmx.notifications.in")
                .handle(Notification.class, (notification, headers) -> {

                    if (!QueueHealth.DEPTH_CHANGED
                            .equals(notification.getType())) {
                        throw new IllegalArgumentException(
                                "Invalid notification type");
                    }

                    Object data = notification.getUserData();
                    if (!(data instanceof Integer depth) || depth < 0) {
                        throw new IllegalArgumentException(
                                "Invalid queue depth");
                    }

                    Object handback = headers.get(
                            JmxHeaders.NOTIFICATION_HANDBACK);

                    String sourceName = handback instanceof String s
                            ? s : "unidentified-queue";

                    sink.record(new QueueDepthEvent(
                            notification.getType(),
                            sourceName,
                            notification.getSequenceNumber(),
                            notification.getTimeStamp(),
                            depth));

                    return null; // One-way event, no reply
                })
                .get();
    }
}
~~~

**Version scope:** This source uses Spring Integration **6.x** imports. For 7.x, `NotificationListeningMessageProducer` resides in package `org.springframework.integration.jmx.inbound`; check your version and update the import accordingly. `JmxHeaders` is a different class from `NotificationListeningMessageProducer`—do not change the packages of all JMX types by guesswork.

### 10.1. MBeanExporter and ObjectName must match

`MBeanExporter.setBeans(Map.of(QUEUE_OBJECT_NAME, queueHealth))` registers the publisher under the ObjectName used by the adapter. If the exporter registers a different name, the adapter will not receive events even though the `QueueHealth` bean exists in the Spring context.

In real environments, the platform MBeanServer may already have an MBean with the same ObjectName. In that case, adjust the naming or registration policy intentionally rather than silently overwriting an MBean managed by another service.

### 10.2. Filter and handback

`NotificationFilter` receives notifications from JMX and only permits type `demo.queue.depth.changed`. Heartbeats are dropped at the listener layer.

`setHandback("orders-queue")` provides source context. The producer places a non-null handback into a JMX-related Spring message header, which the flow reads via `JmxHeaders.NOTIFICATION_HANDBACK`. This is **not** the `Notification.getUserData()` field.

If an adapter uses an ObjectName pattern to listen to multiple MBeans, using the same handback string will not automatically distinguish each MBean. In that case, you need source context with sufficient identity, or to rely on validated and normalized source metadata.

### 10.3. DirectChannel and thread context

`DirectChannel` dispatches to the handler synchronously on the caller thread when receiving a message. If the broadcaster uses synchronous notification delivery, a slow handler can affect the thread emitting the notification. That is why the demo code only writes to a small in-memory sink instead of calling slow DB/HTTP operations directly.

In production, consider an `ExecutorChannel` with a bounded queue, or writing quickly to a durable inbox and processing on a worker. However, switching to an executor does not create durability and also requires async error handling.

### 10.4. Exporter and adapter lifecycle

The following sequence can occur:

~~~text
Spring context creates QueueHealth
Spring creates MBeanExporter
MBeanExporter registers ObjectName
NotificationListeningMessageProducer starts/refreshes
JMX listener is registered
MBean emits Notification
Spring flow receives Message<Notification>
~~~

The initialization order between the exporter and the endpoint is a lifecycle detail that must be verified in deployment. The listener producer implementation includes logic related to `ContextRefreshedEvent` because `MBeanExporter` may finish exporting after the initial start time; do not manually call `adapter.handleNotification(...)` at startup to "patch" unregistered events.

### 10.5. Do not create a second MBeanServer unintentionally

`ManagementFactory.getPlatformMBeanServer()` uses the JVM's platform server. If you use XML `<context:mbean-server/>` or multiple Spring contexts, ensure the exporter and listener reference the **exact same server**. The same ObjectName on **two different MBeanServers** represents two different MBeans, with no automatic cross-server notifications.

## 11. DTO and sink for testing the flow

### 11.1. QueueDepthEvent.java

~~~java
package demo.jmxnotifications;

record QueueDepthEvent(
        String eventType,
        String sourceName,
        long sequenceNumber,
        long occurredAtEpochMillis,
        int depth) {
}
~~~

This DTO uses simple types that are easy to serialize and store. `eventType` has its own contract, `sourceName` comes from the configured handback, and `sequenceNumber` is not a persistent event ID across restarts.

### 11.2. NotificationSink.java

~~~java
package demo.jmxnotifications;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

class NotificationSink {

    private final List<QueueDepthEvent> events =
            new CopyOnWriteArrayList<>();

    void record(QueueDepthEvent event) {
        events.add(event);
    }

    List<QueueDepthEvent> snapshot() {
        return List.copyOf(events);
    }

    void clear() {
        events.clear();
    }
}
~~~

`NotificationSink` is only for demonstration/testing; data is lost when the JVM restarts. For important events, persist them to a database/outbox or a replay-capable broker according to your SLA, and manage idempotency and error handling.

### 11.3. Application entry point

~~~java
package demo.jmxnotifications;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JmxNotificationsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                JmxNotificationsApplication.class, args);
    }
}
~~~

The MBean exporter, adapter, and flow are discovered via component scanning in the same package. `queueHealth.setDepth(25)` can be invoked from an internal service or via a JMX management operation in the lab. Do not assume Spring Boot will periodically emit notifications just because an MBean was created.

## 12. Trying out a notification

Assuming the Spring context is ready and you have the `QueueHealth` bean:

~~~java
queueHealth.setDepth(25);
~~~

The MBean produces:

~~~text
type            = demo.queue.depth.changed
sequenceNumber  = 1
timeStamp       = time the JVM emitted the event
message         = "Orders queue depth changed"
userData        = Integer(25)
~~~

The JMX listener producer receives it and sends the `Notification` payload into `jmx.notifications.in`. The Spring flow validates it, reads the `orders-queue` handback, and records:

~~~text
QueueDepthEvent(
    eventType = "demo.queue.depth.changed",
    sourceName = "orders-queue",
    sequenceNumber = 1,
    occurredAtEpochMillis = ...,
    depth = 25
)
~~~

This is a **one-way pipeline**, not request-reply. No JMX ACK is sent back to the MBean under this mechanism. If a business service needs to invoke an MBean operation and receive a result, use an outbound operation-invoking gateway instead of a notification listener.

### 12.1. Heartbeat will be filtered out

When calling:

~~~java
queueHealth.emitHeartbeat();
~~~

The MBean emits type `demo.queue.heartbeat`. Because the adapter is configured with a `NotificationFilter` allowing only `DEPTH_CHANGED`, the heartbeat does not enter `jmx.notifications.in` (per listener/filter semantics). If you want to store heartbeats as well, update the filter and route the two types to their respective flows without skipping schema validation.

### 12.2. Message and Notification are different objects

~~~text
JMX Notification:
    type, source, sequenceNumber, timeStamp, message, userData

Spring Message<Notification>:
    payload = Notification object
    headers = Spring metadata + optional JMX handback
~~~

Do not assume `Notification.getSequenceNumber()` is Spring's `MessageHeaders.ID` or that `Notification.getSource()` has already been converted into a safe business ID. When forwarding to a downstream message broker, define an explicit mapping contract.

## 13. XML and Java configuration: which should you choose?

| Aspect | XML namespace | Java @Bean |
| --- | --- | --- |
| Adapter declaration | `<int-jmx:notification-listening-channel-adapter>` | `new NotificationListeningMessageProducer()`. |
| ObjectName | `object-name` attribute | `setObjectName(new ObjectName(...))`. |
| MBeanServer | `mbean-server` or default `mbeanServer` bean | `setServer(MBeanServerConnection)`. |
| Notification filter | `notification-filter` reference | `setFilter(NotificationFilter)`. |
| Handback | `handback` reference | `setHandback(Object)`. |
| Output | `channel` attribute | `setOutputChannel(MessageChannel)`. |
| Flow processing | `<int:service-activator>`, router, transformer | `IntegrationFlow.from(...).handle(...)`. |
| Version migration | XSD namespace/API compatibility needs checking. | Java package imports change in 7.x. |

Choose XML if the project already uses integration namespaces cleanly. Choose Java DSL/`@Bean` if you want type-safe configuration alongside Spring Boot and other services. **Avoid configuring the same listener twice** via both XML and Java on the same ObjectName unless you intentionally want duplicate deliveries.

## 14. Using NotificationFilter, Spring Filter, and Router at the right layers

~~~mermaid
flowchart LR
    M[("MBean notifications")]
    NF{"JMX NotificationFilter"}
    AD["NotificationListeningMessageProducer"]
    CH["MessageChannel"]
    VAL{"Validate Notification"}
    ROUTE{"Spring router by type"}
    A["Queue alerts"]
    H["Health metrics"]
    E["Quarantine"]
    M --> NF
    NF -->|"Accepted"| AD --> CH --> VAL --> ROUTE
    VAL -->|"Malformed"| E
    ROUTE -->|"queue.depth.changed"| A
    ROUTE -->|"heartbeat"| H
~~~

**The three layers have distinct responsibilities:**

1. **JMX NotificationFilter:** filters early by type/metadata to avoid sending every notification into Spring.
2. **Spring Filter/Validator:** checks the payload/userData/source contract and rejects invalid events.
3. **Spring Router:** selects the business pipeline based on the normalized notification type.

In the current Java example, the filter only allows `depth.changed`, so the heartbeat branch does not appear. The diagram illustrates the case where the filter is broadened and routes both types; it is not automatically created by the demo configuration.

### 14.1. Do not route based on message text

`Notification.getMessage()` is descriptive text whose wording or language may change. Use `getType()` or `userData` with an explicit schema version, along with a verified MBean identity.

### 14.2. Filters must be lightweight

A `NotificationFilter` runs at the callback boundary, so it should perform fast checks (type/attribute comparisons). Do not call a database/HTTP endpoint or block inside a filter, as that can stall the MBean's notification dispatch path.

### 14.3. An MBean can declare multiple notification types

`getNotificationInfo()` describes the types an MBean may emit, yet the listener must still validate each actual notification. Do not treat the advertised types array as a guarantee that every `userData` has the right class or that all data conforms to a schema.


## 15. JUnit integration test with an in-process MBeanServer

A useful property of JMX is that you can test end-to-end **in the same JVM**, without an MQTT broker, Kafka cluster, or remote JMX connector. The test loads a Spring context containing:

- `QueueHealth` as the MBean publisher;
- `MBeanExporter` registering the MBean with the platform `MBeanServer`;
- `NotificationListeningMessageProducer` receiving JMX callbacks;
- `DirectChannel` together with `IntegrationFlow`;
- `NotificationSink` recording normalized data in RAM.

Unlike a fake test using `input.send(...)`, this test emits a real notification via `NotificationBroadcasterSupport.sendNotification(...)` and verifies that the listener registered successfully. It still does **not** prove remote JMX delivery or downstream persistence.

### 15.1. JmxNotificationFlowTest.java

~~~java
package demo.jmxnotifications;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.ObjectName;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.jmx.NotificationListeningMessageProducer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = JmxNotificationConfiguration.class)
class JmxNotificationFlowTest {

    @Autowired
    QueueHealth queueHealth;

    @Autowired
    NotificationSink sink;

    @Autowired
    MBeanServer mbeanServer;

    @Autowired
    NotificationListeningMessageProducer queueNotificationAdapter;

    @Autowired
    @Qualifier("jmx.notifications.in")
    MessageChannel input;

    @BeforeEach
    void reset() {
        sink.clear();
    }

    @Test
    void mBeanIsRegisteredUnderExpectedObjectName()
            throws Exception {

        var name = new ObjectName(
                "demo.integration:type=QueueHealth,name=Orders");

        assertTrue(mbeanServer.isRegistered(name));
        assertTrue(queueNotificationAdapter.isRunning());
    }

    @Test
    void depthNotificationPassesThroughJmxAdapterAndFlow() {
        queueHealth.setDepth(25);

        assertEquals(1, sink.snapshot().size());

        QueueDepthEvent event = sink.snapshot().get(0);

        assertEquals(QueueHealth.DEPTH_CHANGED,
                event.eventType());
        assertEquals("orders-queue", event.sourceName());
        assertEquals(25, event.depth());
        assertTrue(event.sequenceNumber() > 0);
        assertTrue(event.occurredAtEpochMillis() > 0);
    }

    @Test
    void heartbeatIsRejectedByJmxNotificationFilter() {
        queueHealth.emitHeartbeat();

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void malformedNotificationIsRejectedBySpringFlow() {
        var wrong = new Notification(
                QueueHealth.DEPTH_CHANGED,
                "malformed-source",
                99L);
        wrong.setUserData("not-an-integer");

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder
                        .withPayload(wrong)
                        .build()));

        assertTrue(sink.snapshot().isEmpty());
    }

    @Test
    void stopUnregistersListenerThenStartRestoresIt() {
        queueNotificationAdapter.stop();

        try {
            assertFalse(queueNotificationAdapter.isRunning());

            queueHealth.setDepth(30);
            assertTrue(sink.snapshot().isEmpty());
        } finally {
            queueNotificationAdapter.start();
        }

        queueHealth.setDepth(31);
        assertEquals(1, sink.snapshot().size());
        assertEquals(31, sink.snapshot().get(0).depth());
    }
}
~~~

**Limitations and practical notes:**

- The test uses Spring Integration **6.x** imports; if using 7.x, update the producer package accordingly.
- With `DirectChannel` and the default broadcaster without a custom executor, callbacks and sink recording run synchronously in the demo. If replaced by an executor, you must use await/latch instead of asserting immediately.
- Each test method clears the sink but **does not reset** the publisher's sequence. Therefore, assert only that the sequence is positive rather than asserting an event always has sequence 1.
- The stop/start test uses `try/finally` to avoid leaving the endpoint stopped if an assertion fails. Parallel test suites can interfere with lifecycle; run independently or use isolated test contexts.
- When `MBeanServer` is the platform server, other tests in the same JVM may collide on the ObjectName. `MBeanExporter` must unregister the MBean it manages when the context closes; use distinct names across different test suites.
- `assertThrows(RuntimeException.class)` accounts for Spring wrapping handler exceptions. A thorough QA pass should inspect the cause chain and `errorChannel` on your actual version.

### 15.2. Real-emitter tests vs. fake Message tests

| Test | Source | What is verified |
| --- | --- | --- |
| `input.send(Message<Notification>)` | Fake Spring message. | DTO mapping, validation, and internal handler wiring. |
| `queueHealth.setDepth(...)` | JMX MBean broadcaster. | MBean registration, listener/filter, adapter → channel → handler. |
| JConsole/JMX client invoking operation | JMX management client. | Operation/attribute exposure and local/remote end-to-end events. |
| Remote JMX connector fault test | Network connection to another JMX server. | Auth, connection loss, listener registration, and recovery. |

### 15.3. Testing callback timing when not using DirectChannel

If you change the output to an `ExecutorChannel`, use `CountDownLatch`, Awaitility, or a timed polling assertion on **test state**—do not use `Thread.sleep(1000)` as proof that the system finished processing. Separate the "adapter received" metric from "business handler completed."

## 16. Testing with JConsole or a Java JMX client

JConsole is a JDK tool that can connect to a managed JVM. In a user-controlled lab environment, you can:

1. Run the Spring Boot application with `JmxNotificationConfiguration`.
2. Open JConsole and connect to the **local JVM** (do not open an unauthenticated public remote management port).
3. In the **MBeans** tab, locate `demo.integration:type=QueueHealth,name=Orders`.
4. Confirm that the `Depth` attribute and `emitHeartbeat` operation are present. The `setDepth(...)` setter may appear as a write operation on the `Depth` attribute, depending on the tool UI.
5. Set `Depth` to 25 and observe `QueueDepthEvent` in the application if output logging or sink visibility is configured.
6. Invoke `emitHeartbeat` and verify the flow only receives depth notifications due to the adapter filter.

**Note:** The `NotificationSink` example only stores events in RAM and does not log to the console automatically. To see results directly, add appropriate logging/meters or check `sink.snapshot()` in tests. Seeing the MBean in JConsole does **not** prove the listener adapter registered successfully; verify handler output or metrics.

### 16.1. Java JMX API invoking an operation through MBeanServer

If you want to test without opening a GUI:

~~~java
import java.lang.management.ManagementFactory;

import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "demo.integration:type=QueueHealth,name=Orders");

server.setAttribute(
        name,
        new Attribute("Depth", Integer.valueOf(25)));

Object currentDepth =
        server.getAttribute(name, "Depth");

System.out.println("Depth = " + currentDepth);
~~~

This snippet is a local JMX client. It works once the MBean is registered and the attribute is exported as expected, and it does not start a Spring context on its own. To test through `NotificationListeningMessageProducer`, start the listener application with the matching MBeanServer before setting the attribute.

### 16.2. Testing NotificationFilter standalone

~~~java
import javax.management.Notification;
import javax.management.NotificationFilter;

NotificationFilter filter = notification ->
        QueueHealth.DEPTH_CHANGED.equals(notification.getType());

Notification depth = new Notification(
        QueueHealth.DEPTH_CHANGED, "queue", 1L);

Notification heartbeat = new Notification(
        QueueHealth.HEARTBEAT, "queue", 2L);

assert filter.isNotificationEnabled(depth);
assert !filter.isNotificationEnabled(heartbeat);
~~~

This is a short Java example for unit testing; in JUnit, use `assertTrue/assertFalse` instead of Java `assert` because assertions may be disabled when the JVM runs without `-ea`. Standalone filter tests do not replace the end-to-end MBeanServer test in section 15.

## 17. Listener lifecycle and MBean registration

### 17.1. When does the adapter register the listener?

A Spring-managed `NotificationListeningMessageProducer` is an endpoint with a start/stop lifecycle. On start, it looks up MBean(s) by `ObjectName` and registers a `NotificationListener` with the `MBeanServerConnection`; on stop, it unregisters it.

This differs from `MBeanExporter`, which is responsible for creating or registering the MBean on the server. To receive notifications:

~~~text
MBean exists with correct ObjectName
    +
Listener endpoint is started
    +
NotificationFilter accepts type
    +
MessageChannel has a consumer
    =
Notification can reach the Spring Integration handler
~~~

"Having an adapter bean" is not enough; "having an MBean" is not enough either if the listener is not attached.

### 17.2. MBean registered after the adapter starts

This is common in applications with dynamic MBeans. The adapter may not see the MBean at initial registration time. Spring Integration's listener producer supports cases where `MBeanExporter` initializes late in the Spring context, but you should not assume it tracks **every future registration** indefinitely.

If MBeans are created and removed frequently:

- Design a re-registration mechanism when an MBean appears;
- You can listen for registry change notifications from `MBeanServerDelegate` if appropriate for your JMX API usage;
- Or stop/start/recreate the adapter through a controlled lifecycle controller;
- Test unregistering and re-registering under the same ObjectName;
- Avoid creating duplicate listeners on rebind, which leads to duplicate events.

### 17.3. Stopping does not undo previously processed notifications

`adapter.stop()` detaches the listener and does not roll back side effects already performed by Spring handlers. In-flight callbacks may already have begun before stop; define an application drain/shutdown policy. Do not use stop/start to build retry or exactly-once semantics.

### 17.4. Context refresh and MBeanExporter

In a Spring application, the exporter and listener may participate in different lifecycle phases. The producer implementation handles `ContextRefreshedEvent` to cover cases where the MBean does not yet exist when the listener starts. However, verify actual behavior on your framework version and bean graph. When notifications are missing after startup, enable DEBUG logs for JMX adapter/object name resolution to see which MBeans were subscribed to.

### 17.5. Resources that require cleanup

| Resource | Owner | When to clean up? |
| --- | --- | --- |
| `NotificationListener` registration | Inbound adapter. | Endpoint stop/destroy. |
| `MBean` registration | `MBeanExporter` or manual registration code. | Context close / explicit unregister. |
| Platform `MBeanServer` | JVM/management runtime. | Usually the entire platform server is not destroyed. |
| Remote `JMXConnector` | Code creating the connector or corresponding Spring bean. | Close on shutdown, reconnect/failure recovery. |
| Spring channels/executors | Spring context. | Stop/drain, executor shutdown. |
| Business persistence | Repository/DB. | Retention and transaction policy; do not delete when the listener stops. |

## 18. Remote JMX: MBeanServerConnection, security, and connectivity

`NotificationListeningMessageProducer.setServer(...)` accepts an `MBeanServerConnection`; for a local MBeanServer, `MBeanServer` is also an `MBeanServerConnection`. When using remote JMX, create a properly secured connection and pass it to the adapter.

**Illustrative** API example, not a production-ready connector configuration:

~~~java
import java.util.Map;

import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

// URL/credentials/SSL properties configuration must come from
// security infrastructure; do not hardcode secrets in source code.
JMXServiceURL url = new JMXServiceURL(
        "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi");

JMXConnector connector = JMXConnectorFactory.connect(url);
MBeanServerConnection remote = connector.getMBeanServerConnection();

// adapter.setServer(remote);
// ... When no longer in use, you must call connector.close().
~~~

**Do not run this remote demo on a public port without authentication/TLS.** The URL only illustrates the API; a local test server does not exist automatically. Remote JMX over RMI may require multiple ports, firewall configuration, and dedicated TLS/certificates; `localhost:9999` is not guaranteed to work in Docker/Kubernetes if the connector/RMI hostname is wrong.

### 18.1. Remote JMX security principles

1. Do not expose unauthenticated remote JMX to the Internet.
2. Require TLS and verify server identity/certificates per system policy.
3. Protect credentials in secrets storage and never log them.
4. Restrict network access, firewalls, roles, and permissions by MBean/operation.
5. Restrict untrusted deserialization/class loading configuration; `userData` can be a complex object graph.
6. Subscribe only to required MBeans; do not allow overly broad ObjectName patterns by default.
7. Verify access auditing, connector disconnect/reconnect, and resource cleanup.
8. Consider replacing remote JMX with an agent that exports metrics/events to a broker/HTTPS when security or network topology is unsuitable.

### 18.2. Remote listeners do not automatically replay after network loss

A disconnected JMX connector does not store a notification backlog for absent clients by default. After reconnecting, the client may need to re-register the listener; notifications emitted during the outage may be lost. If event history is required, add a durable store at the MBean source or forwarding agent rather than expecting the connector to recover all events.

### 18.3. Local JMX and remote JMX: do not conflate their SLAs

| Criterion | Local platform MBeanServer | Remote JMX connector |
| --- | --- | --- |
| Network dependency | No remote socket needed for in-JVM callbacks. | Involves network/auth/firewall. |
| Latency | Typically low. | Incurs serialization/RMI/remote callback cost. |
| Fault modes | App/MBean lifecycle, thread blocking. | Adds network partitions, timeouts, connector lifecycle. |
| Security boundary | JVM process and JMX management exposure. | Transport security, credentials, and remote permissions. |
| Replay/durability | Not provided natively. | Not provided natively. |

## 19. Backpressure: a callback is not a worker queue

In the demo, notifications arrive on a `DirectChannel` and the handler runs synchronously. With `NotificationBroadcasterSupport` when no custom executor is supplied, listener invocation can occur on the notification emission path. If the handler performs slow HTTP calls, slow DB queries, or large file writes, the MBean's thread can be impacted.

~~~mermaid
flowchart LR
    M["MBean emits Notification"]
    AD["JMX listener adapter"]
    DIRECT["DirectChannel"]
    BLOCK["Handler calls slow downstream"]
    M --> AD --> DIRECT --> BLOCK
~~~

### 19.1. Switching to a bounded ExecutorChannel

One option is an `ExecutorChannel` with a thread pool and queue bounded to the workload. This can reduce how long the producer is blocked, but you must define:

- Maximum pool size and queue capacity;
- Policy when the executor rejects tasks (reject/backpressure);
- Error channel for exceptions on worker threads;
- Graceful shutdown and draining;
- Backlog and latency monitoring;
- Preventing notification loss if the app crashes before finishing processing.

**ExecutorChannel is not a durable message broker.** If notifications must not be lost across restarts, write quickly to a durable inbox/outbox or push to an appropriate queue/broker and accept the corresponding semantics.

### 19.2. QueueChannel and poller are strictly a downstream decision

A `QueueChannel` can buffer notifications, after which a polling endpoint reads from the queue. In that setup, the poller belongs to the **Spring internal channel**, not the notification-listening adapter. An in-memory queue is not durable by default and can cause backpressure or memory pressure if capacity is unbounded.

### 19.3. Coalescing events intentionally

For continuously changing health metrics, you may only need the latest snapshot rather than every notification; coalescing or rate limiting reduces load. However, do not arbitrarily coalesce critical alerts or audit events where every occurrence must be distinguished. Sampling rules and lost-event tolerance must be documented as a clear SLA.

## 20. Error handling when callbacks or downstream fail

~~~mermaid
flowchart TD
    JMX["JMX Notification"]
    FIL{"NotificationFilter"}
    AD["Listening Adapter"]
    VAL{"Validate payload/type/source"}
    HANDLE["Business handler"]
    OK["Audit / metrics / outbox"]
    ERR["Error channel/quarantine/alert"]
    JMX --> FIL
    FIL -->|"Not matched"| DROP["Ignored"]
    FIL -->|"Matched"| AD --> VAL
    VAL -->|"Valid"| HANDLE --> OK
    VAL -->|"Invalid"| ERR
    HANDLE -. "Downstream exception" .-> ERR
~~~

| Error | Example | Handling |
| --- | --- | --- |
| Listener not registered | MBean not yet exported, adapter not started. | Check objectName/server/lifecycle, test startup order. |
| Notification type filtered out | Heartbeat sent while filter only accepts depth. | Adjust type/filter for the use case. |
| `userData` invalid schema | Integer expected but received String/null. | Reject/quarantine; never cast blindly. |
| Channel has no subscriber | `DirectChannel` has no handler when callback arrives. | Fix wiring/lifecycle, monitor delivery failures. |
| Blocking handler | Slow HTTP/DB on the callback thread. | Bounded async + durable handoff when needed. |
| Handler throws exception | DB outage or mapping error. | Error routing, retry from a durable source; do not rely on JMX redelivery. |
| Remote JMX disconnect | TCP/RMI/credential/cert failure. | Reconnect/re-register, report event gap. |
| MBean unregistered | ObjectName the adapter is listening to disappears. | Rebind via dynamic registry, test lifecycles. |
| Duplicate registration | Same listener attached twice. | Check adapter ownership/bean lifecycle and idempotency. |

### 20.1. A Spring error channel does not mean JMX will redeliver

Spring Integration provides error handling such as `ErrorMessage`/`errorChannel` depending on endpoint/channel configuration. However, once a JMX callback emits a notification, there is no standard default "JMX transaction rollback and redeliver." A downstream Java exception may propagate along the callback/error handler path depending on version and channel; there is **no** guarantee the MBean stores the message for retry.

For critical events, write to an inbox with transactions/idempotency or send to a durable messaging broker; explicitly define the retry source and poison-message policy.

### 20.2. Retries must tie to a business ID or durable state

If the application receives the same alarm again after a restart, the sequence may reset. Do not use `sequenceNumber` alone as a unique key. For each alert, construct a business ID from source identity, instance epoch, and sequence, or include a publisher-managed event ID in the payload, and design an appropriate retention and duplicate policy.

### 20.3. Do not retry malformed notifications indefinitely

A `Notification` with the wrong `userData` type will not fix itself on retry. Quarantine it with a reason code, source type, sequence/timestamp, and safe payload; avoid loops that emit back to the MBean itself and cause a storm.


## 21. Designing observability for a JMX listener

A listener can be "running" yet receive no notifications due to a wrong ObjectName, an unregistered MBean, an overly narrow filter, or a lost connector. Measuring only `application_up=1` is therefore insufficient.

### 21.1. Recommended metrics/fields

| Recommended metric/field | Purpose |
| --- | --- |
| `jmx_listener_running{adapter}` | Whether the endpoint is running per Spring lifecycle. |
| `jmx_registered_mbeans{adapter}` | Number of matching MBeans registered with the listener at observation time. |
| `jmx_notifications_received_total{type}` | Notifications passing through the listener/filter. |
| `jmx_notifications_filtered_total{type}` | Filtered-out notifications, if the implementation exposes an observation hook. |
| `jmx_notification_validation_errors_total` | Payloads/types/sources failing contract validation. |
| `jmx_message_channel_delivery_errors_total` | Errors dispatching to the Spring channel. |
| `jmx_remote_connector_reconnects_total` | Monitoring remote JMX instability. |
| `jmx_notification_processing_latency_ms` | Handler processing time after receipt. |
| `jmx_notification_business_retries_total` | Retries of the business handoff, separate from JMX delivery. |
| `jmx_notification_gap_detected_total` | Sequence gaps **detected**, not a guaranteed count of lost messages. |
| `outbox_backlog_count` | Size of durable work not yet forwarded. |
| `outbox_oldest_age_seconds` | Downstream processing lag. |

The metric names above are **design recommendations**, not names automatically generated by Spring Integration JMX by default. With the appropriate Spring Integration management/metrics version you can collect endpoint/channel stats, but distinguish framework-provided metrics from those recorded by your business handler.

### 21.2. Do not use unbounded ObjectNames/sequences as metric labels

If each tenant/device/MBean has a distinct ObjectName, putting the full ObjectName or sequence into a metric label causes very high cardinality. Use bounded adapter groups, notification types, and roles/namespaces; detailed event IDs belong in structured logs or tracing with access control.

### 21.3. Measuring sequence gaps with caveats

If the same MBean instance emits sequences 100, 101, 103, missing 102 **may** mean a notification was filtered or missed. However, if the MBean restarted and reset its sequence, or multiple types share one sequence, checking requires more context. Do not jump to the conclusion that every gap is a "lost message" without knowing broadcaster semantics and active filters.

### 21.4. Real readiness checks

A readiness check should verify:

1. The `MBeanServerConnection` is still reachable;
2. The target `ObjectName` exists;
3. The listener endpoint is running;
4. A controlled test notification can be emitted and observed reaching the flow, if required by SLA;
5. The downstream broker/DB/inbox is healthy or has appropriate buffering.

Do not continuously emit health-test notifications into a production business stream if they could trigger real alerts. Use a dedicated notification type or test instance.

## 22. Troubleshooting playbook

| Symptom | What to check | Remediation |
| --- | --- | --- |
| `QueueHealth` bean exists but flow sees no events | Is the bean exported as an MBean with the right ObjectName? | Verify `MBeanExporter` and `mbeanServer.isRegistered(...)`. |
| JConsole sees MBean but listener receives nothing | Is the adapter listening to the right MBeanServer and ObjectName? | Check `setServer`/`object-name` and that the endpoint is running. |
| Nothing received right after startup | Listener started before MBean export, or event emitted too early. | Check lifecycle/`ContextRefreshedEvent` and startup readiness. |
| Heartbeat does not arrive | `NotificationFilter` only accepts depth type. | This may be intended behavior; review the type filter contract. |
| `userData` `ClassCastException` | MBean emits a different data type than expected by schema. | Validate with `instanceof`/version instead of casting. |
| `handback` missing from payload | Handback belongs in callback/header, not `userData`. | Read the proper JMX header/API for your version. |
| ObjectName pattern matches incorrectly | Domain/key properties/case/quoting mismatch. | Use `MBeanServer.queryNames` in a test environment to inspect. |
| New dynamic MBean does not send notifications | Listener was not re-registered for the new MBean. | Design refresh/rebind and test dynamic registration. |
| Duplicate notifications | Two adapters/listeners registered; source re-emits; reconnection. | Check adapter ownership and business ID/idempotency. |
| Switched to ExecutorChannel and test fails immediately | Handler runs async; assertion runs too early. | Use await/latch and separate channel acceptance from processing completion. |
| Remote JMX timeout | RMI hostname/firewall/ports/cert/auth. | Check `JMXConnector` configuration; do not disable security. |
| App slows down during notification bursts | `DirectChannel` blocking or queue too large. | Bounded executor/queue, durable inbox, policy-based coalescing. |
| Error channel does not receive exceptions | Endpoint/channel error path differs from expectations. | Test on the exact framework version and configure a dedicated error flow. |
| MBean unregistered while context stays alive | Producer has not rebound. | Lifecycle management and monitoring of `MBeanServer` state. |
| Parallel tests cause MBean collisions | Contexts share the platform server/ObjectName. | Use distinct ObjectNames, serialize tests, or ensure exporter cleanup. |
| Spring Integration 7.x cannot import producer | Class moved from `jmx` to `jmx.inbound`. | Choose the right package for your dependency version. |
| Cannot attach a poller to notification adapter | This endpoint is event-driven. | Use the attribute-polling adapter if you need scheduled attribute reads. |

### 22.1. Minimal runtime checks

In management or test code:

~~~java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
        "demo.integration:type=QueueHealth,name=Orders");

boolean present = mbeanServer.isRegistered(name);
System.out.println("MBean registered: " + present);
~~~

If `present=false`, fix the export/registration first rather than debugging `IntegrationFlow` as if the notification had already reached the channel.

### 22.2. Using selective DEBUG logging

The Spring Integration JMX listener logs discovered/matched MBeans when DEBUG is enabled in supported versions. Enabling DEBUG in a lab helps verify ObjectName resolution and lifecycle; avoid leaving broad debug logging enabled in production for long periods because it may contain sensitive metadata or high log volume.

### 22.3. Distinguish MBean errors from handler errors

If a JMX client calls `setDepth(-1)`, the MBean itself rejects the argument before emitting a notification. If a valid notification is emitted but the Spring flow rejects `userData`, that is a business validation or downstream error. These two failures happen at different locations and require separate metrics and auditing.

## 23. Common anti-patterns

| Anti-pattern | Why it is unsuitable | Fix |
| --- | --- | --- |
| Attaching a poller to "listen" for JMX Notifications | Notification listener is callback/event-driven. | Use notification-listening adapter; pollers are only for attribute polling or internal queues. |
| Treating ObjectName as a Spring channel | They are two different naming spaces. | Clearly separate JMX ObjectName, adapter bean, and channel ID. |
| Casting `notification.getUserData()` straight to DTO | JMX `userData` is `Object`; easy to hit schema mismatches. | Validate type/version and transform explicitly. |
| Routing business logic using `getMessage()` | Human-readable text can change. | Route by `Notification.getType()` and a normalized contract. |
| Making slow HTTP calls directly in the JMX callback | Blocks the publisher/notification delivery thread. | Use bounded async or durable handoff. |
| Assuming JMX notifications have broker QoS/replay | A JMX listener is not a message broker. | Persist to an inbox/outbox or forwarding agent when SLA requires it. |
| Wide-open ObjectName pattern across all MBeans | Increases load, leaks metadata, hard to validate schemas. | Restrict domain/type and apply filters. |
| Treating every `sequenceNumber` as a global event ID | Sequence is scoped to a broadcaster/instance. | Use source identity + epoch + business event ID. |
| Disabling remote JMX auth for convenience | Exposes JVM management to unauthorized access. | Enforce TLS, auth, firewall, and least privilege. |
| Two adapters listening to one MBean due to duplicate config | Downstream receives duplicate events. | Single listener owner, or dedup if fan-out is intentional. |
| Stopping the endpoint and assuming side effects rolled back | `stop` does not undo already-processed messages. | Use idempotent business transitions and an explicit shutdown policy. |
| Equating MBean attributes with an event stream | Attributes are snapshots; Notifications are events. | Choose polling or notifications based on requirements. |
| Adding `spring-boot-starter-actuator` but forgetting `spring-integration-jmx` | Actuator does not provide the notification adapter. | Add the Spring Integration JMX dependency. |

## 24. Hands-on exercise: JMX queue alerting

**Scenario:** An order-processing system has three queues: Orders, Billing, and Notifications. The queue implementation emits JMX notifications when depth crosses thresholds. A Spring Integration service needs to receive the events, record an audit log, and send alerts to a monitoring system.

### 24.1. Exercise requirements

1. Build `QueueHealthMBean`/`QueueHealth` with a writable `Depth` in the lab and `NotificationBroadcasterSupport`.
2. Emit notification type `demo.queue.depth.changed` with `Integer` userData, sequence number, and timestamp.
3. Register three MBeans under `demo.integration:type=QueueHealth,name=Orders|Billing|Notifications` using `MBeanExporter` or `MBeanServer.registerMBean(...)` with lifecycle cleanup.
4. Configure a Spring Integration notification-listening adapter with the ObjectName pattern `demo.integration:type=QueueHealth,name=*`.
5. Use a `NotificationFilter` that only accepts `demo.queue.depth.changed` and drops heartbeats.
6. Route notifications into a `MessageChannel`, validate type/metadata/userData, and convert to a DTO containing the source queue name.
7. Route depth 0–49 to metrics, 50–99 to warning, and 100 or above to critical alert.
8. Do not parse the queue name from free-form `Notification.getMessage()`; derive identity from ObjectName/source metadata or an explicit handback contract.
9. Define a business event ID/source epoch if durable deduplication and auditing across restarts are required.
10. Use a fake audit handler to test the `DirectChannel` flow without remote JMX.
11. Test against a real in-JVM `MBeanServer`: `setDepth` is received, heartbeats are filtered out.
12. Test unregistering and re-registering an MBean: when does the listener rebind, and are there event gaps?
13. Test stopping/starting the adapter and ensure no duplicate registrations occur.
14. Switch to a bounded executor/queue, generate 10,000 notifications, and measure dropped/rejected/backlog/latency.
15. Write alerts to a durable inbox/outbox before sending to HTTP/JMS/AMQP/Kafka to survive downstream outages.
16. Design a quarantine for invalid `userData` without retrying malformed notifications indefinitely.
17. If using remote JMX, verify TLS/auth/ports/firewall, connector close, and reconnect.
18. Build a dashboard showing listener running status, received notifications, processing errors, and downstream lag.
19. Contrast the notification adapter with the attribute-polling adapter for cases where the publisher cannot emit notifications.
20. Explain the delivery limitation: local JMX callbacks do not guarantee replay after the listener goes offline.

### 24.2. Acceptance criteria

The exercise passes if:

- An MBean actually emits `Notification`s and the adapter registers successfully;
- JMX notifications enter the Spring `MessageChannel` **without a poller**;
- Type and userData are validated and the DTO is consistent;
- Alerts match the right thresholds and sources, and no alerts are fired from wrong-type heartbeats;
- Heavy blocking work is not performed directly on the callback path;
- Lifecycle, backpressure, and remote security (where applicable) are tested;
- It is accurately explained that a JMX listener does not provide durability, ACK, or replay on its own.

### 24.3. Advanced suggestions

Build a `Notification` whose `userData` is a standardized DTO containing `alertId`, `queueName`, `depth`, and `severity` instead of an `Integer`. Version the schema and write a matcher on `type` to handle queue saturation, connection pool exhaustion, and circuit-breaker transitions. When forwarding events to Kafka, create a durable outbox with an `eventId` rather than simply serializing the raw `Notification`.

## 25. Self-check questions

1. Is the JMX notification-listening adapter inbound or outbound?
2. Does it work via callback or require a poller?
3. How do the roles of `MBeanServer` and Spring `MessageChannel` differ?
4. What does `ObjectName` identify, and is it the same as a Spring bean ID?
5. What mechanism does `NotificationBroadcasterSupport` support?
6. How must a Standard MBean's interface be named in the example?
7. What is `getNotificationInfo()` used for?
8. How does `Notification.getType()` differ from `getMessage()`?
9. What Java type does `getUserData()` return, and why is validation necessary?
10. Is `getSequenceNumber()` a global event ID durable across restarts?
11. What arguments does `NotificationListener.handleNotification(...)` receive?
12. Is the handback object specified on the publisher side or at listener registration?
13. How does handback differ from `Notification.getUserData()`?
14. What three minimal configuration items does the XML adapter require?
15. What is the default MBeanServer bean name in the XML namespace?
16. When is the `mbean-server` attribute needed?
17. Why can an ObjectName pattern match multiple MBeans?
18. Does a pattern guarantee automatically attaching to every new MBean created after startup?
19. How do `NotificationFilter` and Spring business validation differ?
20. What object does the JMX listener producer place into the Spring message payload?
21. How does the Java package of `NotificationListeningMessageProducer` differ between Spring Integration 6.x and 7.x?
22. How can using `DirectChannel` slow down the notification-emitting thread?
23. Does `ExecutorChannel` make JMX notifications durable messages?
24. If the listener is offline when an MBean emits an alert, does JMX store the alert for replay?
25. Does stopping the adapter automatically roll back handlers that already ran?
26. If a remote JMX connector disconnects, what happens to missed notifications?
27. Why does remote JMX require TLS, authentication, and firewalling?
28. How does testing `input.send(Message<Notification>)` differ from testing `queueHealth.setDepth(...)`?
29. Why must you still choose the matching `ObjectName` for the adapter even when using Spring `MBeanExporter`?
30. When forwarding notifications to JMS/AMQP/Kafka, how must idempotency and durability be handled?
31. Why is filtering notifications by human-readable `message` error-prone?
32. When an MBean source emits multiple notification types, what information should the flow route on?
33. If a new MBean matching an ObjectName pattern appears after the adapter has started, what should you check?
34. When receiving a notification with invalid `userData`, should you retry it indefinitely?
35. Which metrics indicate whether the adapter is running, receiving messages, and experiencing downstream errors?

**Hint:** Remember the three main layers: **JMX publisher/MBeanServer → notification-listening adapter → Spring MessageChannel/IntegrationFlow**. This adapter is **event-driven**, not a polling source, and `Notification` does not provide messaging-broker durability or transactions.

## 26. Summary and references

The **JMX notification-listening adapter** lets you use Spring Integration as an ingestion point for JVM management events:

- `NotificationBroadcaster` emits `Notification`s through a JMX MBean.
- `MBeanServer` identifies sources by `ObjectName` and manages listener registration.
- `NotificationListeningMessageProducer` is a Spring Integration inbound endpoint that creates `Message<Notification>` and registers/unregisters the listener with the lifecycle.
- Both the XML namespace `notification-listening-channel-adapter` and Java `@Bean` configuration can set the ObjectName, MBeanServer, NotificationFilter, handback, and output channel.
- The adapter is **event-driven** and requires no poller; `DirectChannel` is synchronous, so threading and backpressure must be considered.
- When MBeans are created dynamically or remote JMX disconnects, do not assume notifications automatically replay or that the listener automatically attaches to every future source.
- Always validate notification type, `userData`, source, and schema before routing or outbound dispatch.
- Secure remote JMX with TLS, auth, and network restrictions; use a durable inbox/outbox and idempotency if the business requires stronger delivery guarantees than callbacks.

In the **SPRING_INTEGRATION_ADAPTERS** module, the JMX notification adapter is an entry point into the same system of channels, flows, and handlers used for files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. By cleanly separating **JMX callback → normalized Spring message → business processing → downstream handoff**, an application gains visibility into JVM events without confusing monitoring signals with storage-guaranteed business transactions.

### 26.1. Official sources for API/version verification

- [Spring Integration – JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html): describes the notification-listening channel adapter, XML namespace, ObjectName patterns, filter/handback, and event-driven principles.
- [Spring Integration 6.5 – NotificationListeningMessageProducer Javadoc](https://www.springframework.org/spring-integration/docs/6.5.0/api/org/springframework/integration/jmx/NotificationListeningMessageProducer.html): API for `org.springframework.integration.jmx.NotificationListeningMessageProducer`.
- [Spring Integration 7.x – NotificationListeningMessageProducer Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/jmx/inbound/NotificationListeningMessageProducer.html): class moved to the `jmx.inbound` package.
- [Java Platform – javax.management](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/package-summary.html): fundamentals of `MBeanServer`, `ObjectName`, `Notification`, `NotificationBroadcasterSupport`, `NotificationFilter`, and `NotificationListener`.

When applying this in a real project, verify dependency versions and run JMX registration/lifecycle tests in your deployment environment. The code snippets in this lesson are STEP 4 learning materials and do **not** replace Content QA/refactoring or thorough integration verification.



