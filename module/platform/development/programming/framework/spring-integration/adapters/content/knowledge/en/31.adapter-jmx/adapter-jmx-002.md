# JMX attribute-polling adapter

## 1. Problem: bringing MBean state into Spring Integration

A Java application exposes a JMX MBean to monitor the `Orders` queue. The MBean has a `Depth` attribute (the number of pending items), but **does not emit a JMX Notification** when the value changes. The system wants to read `Depth` every five seconds and feed it into Spring Integration to record metrics, check thresholds, and emit alerts.

This is the role of the **JMX attribute-polling adapter**: a Spring Integration **inbound adapter** that uses a **poller** to proactively call `MBeanServerConnection.getAttribute(ObjectName, attributeName)` on a schedule, wrap the value into a Spring `Message<?>`, and send it to a `MessageChannel`.

The lesson **“JMX attribute-polling adapter”** belongs to the **Adapter JMX** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. This module teaches how to connect external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing file, SFTP, HTTP, JMS, AMQP, Kafka, and database exchange, message contract handling, error handling, and connection lifecycles. JMX attribute polling is a source of **JVM management state** brought into that same message pipeline.

After this lesson, the learner will be able to:

1. Distinguish JMX `MBeanServer`, `MBeanServerConnection`, `ObjectName`, attributes, operations, and notifications.
2. Configure the native `int-jmx:attribute-polling-channel-adapter` with `object-name`, `attribute-name`, output channel, and poller.
3. Build an equivalent configuration using `@InboundChannelAdapter` and `MessageSource<?>` when custom reading/normalization in Java is needed.
4. Write a Standard MBean, export it with `MBeanExporter`, and read snapshots via `getAttribute(...)`.
5. Understand Integer/Boolean/String return types and JMX OpenType/`CompositeData`.
6. Distinguish sampled snapshots from state-change events, avoiding alert spam and missed transitions between polls.
7. Design intervals, backpressure, retries, lifecycle, remote JMX security, and monitoring.
8. Write JUnit tests using an in-process MBeanServer, verifying the Spring message contract, getter errors, and scheduled polling behavior.
9. Choose a notification-listening adapter or a durable broker when requirements exceed what sampling can provide.

**Core point:** a JMX attribute poll reads a **snapshot at the moment of polling**, without automatically knowing the full history of changes between two reads. The produced Spring message is **not** a JMX `Notification` object.

## 2. Diagram: MBean attribute → poller → MessageChannel

~~~mermaid
flowchart LR
    M["QueueStats MBean<br/>getDepth()"]
    S[("MBeanServer")]
    P["Spring Poller<br/>fixed-delay=5s"]
    A["JMX Attribute Polling Source<br/>getAttribute()"]
    C["jmx.queue.depth.in<br/>MessageChannel"]
    F["IntegrationFlow<br/>normalize/filter/route"]
    MET["Metrics / Audit"]
    EXT["HTTP / JMS / AMQP / Kafka"]
    M --> S
    P --> A
    A -->|"Read JMX attribute"| S
    A -->|"Spring Message<value>"| C --> F
    F --> MET
    F --> EXT
~~~

One polling cycle:

1. The poller fires and invokes `receive()` on the JMX polling source.
2. The source uses `MBeanServerConnection` and `ObjectName` to call `getAttribute()`.
3. If the result is valid, the value becomes the Spring message payload and is sent to the output channel.
4. `IntegrationFlow` validates the data type, converts it to a DTO, records metrics, or dispatches outbound.
5. The next cycle reads the current snapshot again and does **not** replay old snapshots.
6. Stopping the endpoint stops the poller from reading; the MBean can still remain on the `MBeanServer`.

### 2.1. A poller is not a JMX NotificationListener

~~~text
12:00:00 poll → Depth=3
12:00:05 poll → Depth=3
12:00:10 poll → Depth=9
12:00:15 poll → Depth=2
~~~

If `Depth` rises from 3 to 100 and returns to 3 between 12:00:00 and 12:00:05, the poller **can completely miss** the spike of 100. When every state transition must be captured, consider a notification-listening adapter or an event/outbox at the source.

### 2.2. Component boundaries

| Component | Responsibility | What it is not |
| --- | --- | --- |
| MBean | Exposes state/operations over JMX. | A Spring `MessageChannel`. |
| MBeanServer | Registry providing `getAttribute`/metadata. | An MQTT/JMS broker. |
| Poller | Decides when and how often to read the source. | A change log of business state. |
| Attribute polling source | Reads a single JMX attribute. | A notification subscription. |
| MessageChannel | Delivers messages to Spring endpoints. | A default persistent event log. |
| IntegrationFlow | Validates, transforms, routes, persists/sends outbound. | A JMX protocol implementation. |

### 2.3. No automatic business ACK

A `getAttribute()` call returning `Depth=25` only reports the value at read time; it has no MQTT PUBACK, Kafka offset, transaction commit, or JMX reply confirming that an operator received an alert. Downstream durability and acknowledgement belong to application architecture.

## 3. Essential JMX fundamentals

### 3.1. Standard MBean and attribute names

A Standard MBean typically has an interface `QueueStatsMBean` and class `QueueStats`. Getter/setter conventions:

~~~java
public interface QueueStatsMBean {
    int getDepth();
    boolean isHealthy();
    void setDepth(int value);
    void resetCounters();
}
~~~

| Java method | JMX entity | Attribute name |
| --- | --- | --- |
| `getDepth()` | Readable attribute | `Depth` |
| `setDepth(int)` | Writable part of attribute | `Depth` |
| `isHealthy()` | Readable boolean attribute | `Healthy` |
| `resetCounters()` | Operation | Do not use `getAttribute`. |

**Common mistake:** configuring `attribute-name="getDepth"` instead of `attribute-name="Depth"`. Attribute names are case-sensitive and do not include the Java `get` prefix.

### 3.2. MBeanServer and MBeanServerConnection

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

MBeanServer local = ManagementFactory.getPlatformMBeanServer();
MBeanServerConnection connection = local;

Integer depth = (Integer) connection.getAttribute(
        new ObjectName("demo.integration:type=QueueStats,name=Orders"),
        "Depth");
~~~

`MBeanServer` implements `MBeanServerConnection`. Clients can use the common interface for both local servers and remote JMX connectors; remote usage also introduces `IOException`/TLS/RMI/network failure modes.

### 3.3. ObjectName is not a Spring channel

~~~text
demo.integration:type=QueueStats,name=Orders
java.lang:type=Memory
java.lang:type=Threading
java.lang:type=ClassLoading
~~~

An `ObjectName` has a domain and key properties. To read a specific attribute, you generally must specify a **concrete MBean**: do not treat an `ObjectName` pattern matching multiple MBeans as a single `getAttribute` returning multiple values. If you want to inventory multiple MBeans, use `queryNames`/custom aggregation or an appropriate JMX tree source.

### 3.4. MBeanInfo helps discover attribute names

~~~java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = connection.getMBeanInfo(
        new ObjectName("demo.integration:type=QueueStats,name=Orders"));

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.println(
            attr.getName() + " readable=" + attr.isReadable()
            + " type=" + attr.getType());
}
~~~

If `AttributeNotFoundException` occurs, verify that the MBean exposes `Depth` and that it is readable, rather than retrying infinitely or guessing getter names.

### 3.5. JMX OpenType and CompositeData

Standard MXBeans such as `java.lang:type=Memory` expose `HeapMemoryUsage`. When read via JMX, the result can be a `javax.management.openmbean.CompositeData` rather than a simple `Long`.

~~~java
import java.lang.management.MemoryUsage;
import javax.management.openmbean.CompositeData;

Object result = connection.getAttribute(
        new ObjectName("java.lang:type=Memory"),
        "HeapMemoryUsage");

if (result instanceof CompositeData composite) {
    MemoryUsage usage = MemoryUsage.from(composite);
    long usedBytes = usage.getUsed();
}
~~~

Do not cast directly with `(Long) result` or send raw OpenType values to HTTP/Kafka without an explicit schema serializer.

## 4. Comparing attribute-polling and notification-listening

| Criterion | Attribute-polling | Notification-listening |
| --- | --- | --- |
| What must the MBean have? | Readable attribute/getter. | `NotificationBroadcaster` emitting `Notification`. |
| Trigger | Poller periodically calls `getAttribute`. | JMX `NotificationListener` callback. |
| Needs a poller? | **Yes.** | No. |
| Payload | Attribute value (snapshot). | `javax.management.Notification`. |
| Unchanged value | Can produce the same snapshot on each read. | Does not emit automatically unless broadcaster sends one. |
| Rapid changes between reads | Can miss transitions. | Can receive them if listener is registered and events are emitted. |
| Load on MBean | Each poll invokes the getter, which may cost resources. | Broadcaster creates event; listener runs callback. |
| Offline replay | Not provided natively. | Not provided natively. |
| Use case | Gauges, health values, configuration snapshots. | Alerts/transitions/event-driven monitoring. |

If you need **every individual event** with strong replay/ACK, you may need to add an outbox/broker or CDC instead of forcing a poller to act as an event log.

## 5. Native Spring Integration XML adapter

Spring Integration supports the `int-jmx:attribute-polling-channel-adapter` element. A minimal configuration:

~~~xml
<int-jmx:attribute-polling-channel-adapter
        id="ordersDepthAdapter"
        mbean-server="mbeanServer"
        object-name="demo.integration:type=QueueStats,name=Orders"
        attribute-name="Depth"
        channel="jmxQueueDepth">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-jmx:attribute-polling-channel-adapter>
~~~

- `id`: Spring endpoint ID.
- `mbean-server`: `MBeanServer`/connection bean used for reading.
- `object-name`: exact MBean name.
- `attribute-name`: readable attribute name, e.g. `Depth`.
- `channel`: Spring output `MessageChannel`.
- `fixed-delay="5000"`: delay between polls in **milliseconds**.
- `max-messages-per-poll="1"`: limits the number of `receive()` calls in a single poll task.

**This is the native JMX polling adapter.** It differs from writing a custom Java timer that calls JMX or registering a notification listener callback.

### 5.1. XML wiring with MBeanServer and service activator

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

    <int:channel id="jmxQueueDepth"/>

    <int-jmx:attribute-polling-channel-adapter
            id="ordersDepthAdapter"
            mbean-server="mbeanServer"
            object-name="demo.integration:type=QueueStats,name=Orders"
            attribute-name="Depth"
            channel="jmxQueueDepth">
        <int:poller fixed-delay="5000"
                    max-messages-per-poll="1"/>
    </int-jmx:attribute-polling-channel-adapter>

    <bean id="depthLogHandler" class="demo.jmxpolling.DepthLogHandler"/>

    <int:service-activator
            input-channel="jmxQueueDepth"
            ref="depthLogHandler"
            method="handle"/>
</beans>
~~~

For this XML to work, a real MBean must be registered on the **same** `MBeanServer` with the `ObjectName` above. This context creates the server, channel, adapter, and handler, and **does not automatically export** the `QueueStats` MBean.

### 5.2. Corresponding small handler

~~~java
package demo.jmxpolling;

public class DepthLogHandler {

    public void handle(Integer depth) {
        System.out.println("Orders queue depth: " + depth);
    }
}
~~~

Direct logging is only for lab use. In production, normalize the snapshot, record metrics, implement error handling, and avoid calling slow external services directly on the poller thread.

### 5.3. Do not create two pollers for the same data unintentionally

If Spring Boot imports the XML above while also enabling a Java `@InboundChannelAdapter` reading the same attribute, both endpoints will produce two samples per interval. This is not an MQTT duplicate, but **two independent reads**, which can cause alert spam or skewed metrics.

## 6. Poller: interval, concurrency, and resolution

### 6.1. fixed-delay, fixed-rate, and cron

| Trigger | Meaning | What to measure |
| --- | --- | --- |
| `fixed-delay="5000"` | Waits a fixed duration between executions after the previous one completes per scheduler semantics. | MBean getter latency affects sample cadence. |
| `fixed-rate="5000"` | Scheduled to run at a steady cadence. | When tasks are slow or pools have multiple threads, watch for overlap/delay. |
| Cron | Polls at specific calendar times. | Timezone/DST and intervals without samples. |

Do not set `max-messages-per-poll="1000"` hoping to read 1,000 different values from one attribute: the source will repeatedly read the same snapshot within one task, increasing load and producing duplicate-content messages.

### 6.2. A poll is not a business event

~~~text
poll #1: Depth=25
poll #2: Depth=25
poll #3: Depth=25
~~~

These three messages are three **snapshots**, not a protocol error. For gauge metrics, repeated updates are fine. If every sample with `Depth>=25` triggers an email, add a state-transition filter or cooldown/hysteresis—not a QoS change, because JMX has no MQTT QoS.

### 6.3. Short-lived spikes can be missed

~~~text
12:00:01 Depth=10
12:00:02 Depth=200
12:00:03 Depth=0
12:00:05 poll → Depth=0
~~~

A 5-second poll interval misses the spike to 200. Shortening the interval increases resolution but also increases MBean getter calls, CPU/network load, and downstream processing. If the SLA requires catching every spike, the source must emit events or maintain a `maxSinceLastPoll` attribute with a reset contract.

### 6.4. Concurrency and ordering

With a single simple endpoint/poller, polls generally run sequentially. If you add an executor, multiple app replicas, or multiple endpoints, reads can run in parallel and snapshots may arrive downstream out of strict order. Include `observedAt` and source identity, and do not sum snapshots as transactional events.

## 7. Snapshot message contract and conversion

The native source puts the raw value returned by JMX into the Spring message payload. For `QueueStats`, that might be `Integer(25)`:

~~~text
Spring Message:
  payload = Integer(25)
  headers = Spring message metadata
~~~

If you need the source and sampling timestamp to send over HTTP/Kafka, construct a DTO yourself:

~~~json
{
  "source": "demo.integration:type=QueueStats,name=Orders",
  "attribute": "Depth",
  "value": 25,
  "observedAt": "2026-11-23T03:15:00Z",
  "schemaVersion": 1,
  "kind": "JMX_ATTRIBUTE_SNAPSHOT"
}
~~~

This is an **illustrative application schema**, not JSON emitted automatically by the adapter. `observedAt` is when the application read/packaged the snapshot, **not** when the attribute actually changed.

| Field | Role |
| --- | --- |
| `source` / `objectName` | Controlled MBean identity. |
| `attribute` | Name of the readable JMX attribute. |
| `value` | Validated/converted value. |
| `observedAt` | Sampling timestamp. |
| `schemaVersion` | Outbound contract version. |
| `readStatus` | Success/error/gap if the model stores history. |

### 7.1. OpenType and JSON

JMX `CompositeData`/`TabularData` are not guaranteed to serialize cleanly to every destination. Mapping explicitly into Java records with primitives/`String`/`Instant` ensures HTTP/JMS/Kafka/file/SFTP adapters receive a stable, testable contract.

### 7.2. Do not confuse sample time with update time

The queue may have reached 25 long before; a snapshot at 12:00:05 only proves the app observed 25 at that moment. If you need the actual change timestamp, the MBean must expose additional metadata or emit a JMX Notification.


## 8. JMX attribute read errors and recovery

| Error | Cause | Handling policy |
| --- | --- | --- |
| `InstanceNotFoundException` | MBean not registered yet, wrong ObjectName, or already unregistered. | Check lifecycle/source; retry on schedule if the MBean can reappear. |
| `AttributeNotFoundException` | Wrong name/case or attribute is not readable. | Check `MBeanInfo`, fix schema; avoid infinite retries. |
| `MBeanException` | MBean getter threw an internal exception. | Inspect cause; distinguish permanent vs. transient errors. |
| `ReflectionException` | Incompatible JMX invocation/reflection. | Fix MBean implementation/metadata. |
| `IOException` on remote | Connector/RMI/network/TLS error. | Reconnect with backoff and record sample gap. |
| `SecurityException` | Insufficient permissions to read the JMX attribute. | Check authentication/authorization; never disable security. |
| Wrong value type / null | MBean contract changed or value unknown. | Validate type/quality; never cast blindly. |
| Slow/blocking getter | Slow MBean or high remote latency. | Limit sampling; monitor timeouts/liveness. |
| Channel has no consumer | Flow not started or wiring error. | Check endpoint status and message dispatch. |
| Downstream handler error | DB/HTTP/Kafka unavailable. | Error flow, durable handoff if events are critical. |

### 8.1. No message does not mean the value stayed the same

If the source returns null or throws an exception, a polling endpoint may not emit a Spring message. "No message observed" can therefore indicate an MBean/source failure or filtering, **not** proof that the snapshot remained unchanged.

### 8.2. The next poll does not replay a missed sample

If the 12:00:05 poll fails, the 12:00:10 poll reads **the current value**; the adapter does not retroactively recover the exact state at 12:00:05. To preserve all changes, the source must expose history/notifications or publish to a durable system.

### 8.3. Error channel is part of Spring, not a JMX ACK

Spring Integration provides `ErrorMessage`/`errorChannel`, advice, and task-scheduler error handling depending on endpoint/version. A handler throwing an exception does not cause `MBeanServer` to "redeliver" the attribute snapshot already read. You need metrics for poll failures, retry budgets, and a fail-safe business policy.

## 9. JVM platform example: HeapMemoryUsage

The JVM includes the `java.lang:type=Memory` MBean with the `HeapMemoryUsage` attribute, so you do not need to create a custom MBean to try polling.

~~~xml
<int-jmx:attribute-polling-channel-adapter
        id="heapUsagePoller"
        mbean-server="mbeanServer"
        channel="jmxHeapUsage"
        object-name="java.lang:type=Memory"
        attribute-name="HeapMemoryUsage">
    <int:poller fixed-delay="10000"
                max-messages-per-poll="1"/>
</int-jmx:attribute-polling-channel-adapter>
~~~

`HeapMemoryUsage` may be a `CompositeData`; map it to a clear contract:

~~~java
import java.lang.management.MemoryUsage;
import javax.management.openmbean.CompositeData;

public record HeapSample(
        long usedBytes, long committedBytes,
        long maxBytes, long sampledAtEpochMillis) {

    public static HeapSample fromJmxValue(Object value) {
        final MemoryUsage usage;
        if (value instanceof CompositeData data) {
            usage = MemoryUsage.from(data);
        } else if (value instanceof MemoryUsage direct) {
            usage = direct;
        } else {
            throw new IllegalArgumentException(
                    "Invalid HeapMemoryUsage type");
        }
        return new HeapSample(
                usage.getUsed(),
                usage.getCommitted(),
                usage.getMax(),
                System.currentTimeMillis());
    }
}
~~~

This helper is **not a default Spring Integration class**. In the XML flow, declare a transformer/handler that invokes `HeapSample.fromJmxValue` on the received payload.

### 9.1. Units and max limit

`MemoryUsage` values are in **bytes**. For MiB, divide by 1,048,576. `getMax()` can be negative when undefined, so do not compute `used/max` if max ≤ 0. Instead of firing an email every time heap >80%, use alert state transitions and hysteresis.

### 9.2. Actuator/Micrometer or JMX?

Spring Boot Actuator/Micrometer already provides many JVM metrics out of the box. JMX polling is appropriate when the project needs to read **custom MBeans or legacy library MBeans** into Spring Integration, and is unnecessary for JVM stats already exposed via metrics APIs.

## 10. Spring Boot example: writing a Java MBean reader

The demo clearly distinguishes two options:

- **Native JMX attribute-polling adapter:** XML namespace from section 5, using the framework's JMX source.
- **Semantically equivalent Java bridge:** `@InboundChannelAdapter` + `MessageSource<QueueDepthSnapshot>` calling `MBeanServerConnection.getAttribute(...)`. This is a custom reader implementation when you want to normalize source/value/time right at read time, **not claimed to be the native JMX source class itself**.

### 10.1. Maven dependencies

Java 17+, Spring Boot BOM with compatible versions:

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

Native XML uses `spring-integration-jmx`; the Java bridge relies on JDK `java.management` and Spring Integration polling annotation support. Do not mix major versions arbitrarily.

### 10.2. Project structure

~~~text
src/main/java/demo/jmxpolling/
    JmxPollingApplication.java
    QueueStatsMBean.java
    QueueStats.java
    QueueDepthSnapshot.java
    QueueDepthReader.java
    QueueSnapshotSink.java
    JmxPollingConfiguration.java
src/test/java/demo/jmxpolling/
    QueueDepthReaderTest.java
    JmxPollingFlowTest.java
~~~

### 10.3. Standard MBean interface

~~~java
package demo.jmxpolling;

public interface QueueStatsMBean {

    int getDepth();
    void setDepth(int value);
    boolean isHealthy();
    void resetCounters();
}
~~~

`Depth` and `Healthy` are readable JMX attributes; `resetCounters` is an operation. Spring polling will only read `Depth`.

### 10.4. QueueStats.java

~~~java
package demo.jmxpolling;

import java.util.concurrent.atomic.AtomicInteger;

public class QueueStats implements QueueStatsMBean {

    private final AtomicInteger depth = new AtomicInteger();

    @Override
    public int getDepth() {
        return depth.get();
    }

    @Override
    public void setDepth(int value) {
        if (value < 0) {
            throw new IllegalArgumentException(
                    "Depth must not be negative");
        }
        depth.set(value);
    }

    @Override
    public boolean isHealthy() {
        return depth.get() < 100;
    }

    @Override
    public void resetCounters() {
        depth.set(0);
    }
}
~~~

`setDepth` lets the lab change values easily. Do not expose setters or operations to untrusted remote clients; JMX management permissions must be tightly controlled.

### 10.5. QueueDepthSnapshot.java

~~~java
package demo.jmxpolling;

import java.time.Instant;

record QueueDepthSnapshot(
        String objectName,
        int depth,
        Instant observedAt) {

    QueueDepthSnapshot {
        if (objectName == null || objectName.isBlank()) {
            throw new IllegalArgumentException(
                    "ObjectName is missing");
        }
        if (depth < 0 || observedAt == null) {
            throw new IllegalArgumentException(
                    "Invalid snapshot");
        }
    }
}
~~~

`QueueDepthSnapshot` is an application-defined DTO. `observedAt` marks when the state was **read**, not when the state changed.

### 10.6. QueueDepthReader.java

~~~java
package demo.jmxpolling;

import java.io.IOException;
import java.time.Instant;

import javax.management.JMException;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

class QueueDepthReader {

    private final MBeanServerConnection connection;
    private final ObjectName objectName;

    QueueDepthReader(
            MBeanServerConnection connection,
            ObjectName objectName) {
        this.connection = connection;
        this.objectName = objectName;
    }

    QueueDepthSnapshot read() {
        try {
            Object value = connection.getAttribute(
                    objectName, "Depth");

            if (!(value instanceof Integer depth)) {
                throw new IllegalArgumentException(
                        "Depth must be an Integer");
            }

            return new QueueDepthSnapshot(
                    objectName.getCanonicalName(),
                    depth,
                    Instant.now());
        } catch (JMException | IOException ex) {
            throw new IllegalStateException(
                    "Failed to read JMX Depth: " + objectName, ex);
        }
    }
}
~~~

Benefits: encapsulates all JMX API calls, is easy to test against a local or remote server, and avoids embedding schedulers or threads inside the reader. `MBeanServerConnection.getAttribute` can throw `JMException` and remote `IOException`; the code preserves the exception cause for troubleshooting.

### 10.7. QueueSnapshotSink.java

~~~java
package demo.jmxpolling;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

class QueueSnapshotSink {

    private final List<QueueDepthSnapshot> items =
            new CopyOnWriteArrayList<>();

    void record(QueueDepthSnapshot value) {
        items.add(value);
    }

    List<QueueDepthSnapshot> snapshot() {
        return List.copyOf(items);
    }

    void clear() {
        items.clear();
    }
}
~~~

The in-memory sink is strictly for lab use and has no retention limits or durability; production should use a metrics/time-series DB or inbox/outbox to store important events. Never accumulate periodic samples indefinitely in a `CopyOnWriteArrayList` on a long-running server.

### 10.8. Configuring MBeanExporter, poller, and IntegrationFlow

~~~java
package demo.jmxpolling;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
class JmxPollingConfiguration {

    private static final String OBJECT_NAME =
            "demo.integration:type=QueueStats,name=Orders";

    @Bean(name = "mbeanServer")
    MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    QueueStats queueStats() {
        return new QueueStats();
    }

    @Bean
    MBeanExporter queueStatsExporter(
            MBeanServer mbeanServer,
            QueueStats queueStats) {

        var exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setBeans(Map.of(OBJECT_NAME, queueStats));
        return exporter;
    }

    @Bean
    QueueDepthReader queueDepthReader(
            MBeanServer mbeanServer) throws Exception {
        return new QueueDepthReader(
                mbeanServer, new ObjectName(OBJECT_NAME));
    }

    @Bean(name = "jmx.queue.depth.raw")
    MessageChannel queueDepthInput() {
        return new DirectChannel();
    }

    @Bean
    @InboundChannelAdapter(
            channel = "jmx.queue.depth.raw",
            poller = @Poller(
                    fixedDelay = "5000",
                    maxMessagesPerPoll = "1"))
    MessageSource<QueueDepthSnapshot> queueDepthSource(
            QueueDepthReader reader) {

        return () -> MessageBuilder
                .withPayload(reader.read())
                .build();
    }

    @Bean
    QueueSnapshotSink queueSnapshotSink() {
        return new QueueSnapshotSink();
    }

    @Bean
    IntegrationFlow queueDepthFlow(QueueSnapshotSink sink) {
        return IntegrationFlow.from("jmx.queue.depth.raw")
                .handle(QueueDepthSnapshot.class,
                        (snapshot, headers) -> {
                            sink.record(snapshot);
                            return null;
                        })
                .get();
    }
}
~~~

Explanation:

1. `MBeanExporter` registers the Standard MBean under `OBJECT_NAME`.
2. `@InboundChannelAdapter` creates a Spring polling endpoint for `MessageSource`.
3. `@Poller(fixedDelay="5000")` schedules `receive()` calls each cycle.
4. The source reads JMX, normalizes into a DTO, and builds a Spring `Message`.
5. `DirectChannel` passes the message to `IntegrationFlow`, and the sink records the sample.
6. `return null` in the handler indicates a one-way flow with no reply.
7. This Java source is not the native JMX source class; it is an appropriate configuration approach when custom payload/logic is needed.
8. Do not add an XML adapter for the same source/channel unless you intentionally want double sampling.

### 10.9. Application entry point

~~~java
package demo.jmxpolling;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JmxPollingApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                JmxPollingApplication.class, args);
    }
}
~~~

The application uses the in-JVM platform `MBeanServer` and does not require remote JMX. Make sure the `ObjectName` is not already taken by another MBean and that the exporter starts before the first poll needs to read; when startup order is complex, test readiness and handle `InstanceNotFoundException` properly.

## 11. Runtime flow and snapshot semantics

~~~text
QueueStats bean
   ↓  MBeanExporter registers
MBeanServer: demo.integration:type=QueueStats,name=Orders
   ↓  @InboundChannelAdapter / @Poller
QueueDepthReader.read() → Message<QueueDepthSnapshot>
   ↓
jmx.queue.depth.raw → IntegrationFlow → QueueSnapshotSink
~~~

Invoking from a service in the lab:

~~~java
queueStats.setDepth(25);
~~~

A subsequent poll might record:

~~~text
QueueDepthSnapshot(
  objectName="demo.integration:name=Orders,type=QueueStats",
  depth=25,
  observedAt=2026-11-23T03:15:00Z
)
~~~

`ObjectName.getCanonicalName()` may reorder key properties; both forms still identify the same MBean. Do not assert raw property order strings without accounting for canonical form.

### 11.1. Three identical polls are not three changes

If polling receives `depth=25` three times, those are three **observations**. For gauge monitoring, this is normal; for email alerts, you need a stateful filter/cooldown so you do not send three "just increased to 25" alerts.

### 11.2. When the MBean is not registered in time

`MBeanExporter` and the inbound endpoint have separate lifecycles. In complex configurations, the first poll may run before the MBean exists; log the poll failure, review startup dependencies, and continue on the next cycle according to policy. Never silently return `0` when `getAttribute` fails, as that produces false reporting.


## 12. Transition-based alerting: avoiding alerts every cycle

Suppose a queue is considered overloaded when `Depth>=80`. A Spring filter containing only:

~~~java
snapshot.depth() >= 80
~~~

will pass **every sample** while the queue remains at 80–100. If polling every 5 seconds, a queue overloaded for 30 minutes would send hundreds of emails. To fire only on transitions, you must remember alert state.

### 12.1. Simple severity tracker

~~~java
package demo.jmxpolling;

import java.util.concurrent.atomic.AtomicReference;

enum QueueSeverity {
    NORMAL, WARNING, CRITICAL
}

class QueueSeverityTracker {

    private final AtomicReference<QueueSeverity> previous =
            new AtomicReference<>(QueueSeverity.NORMAL);

    QueueSeverity classify(int depth) {
        if (depth >= 120) {
            return QueueSeverity.CRITICAL;
        }
        if (depth >= 80) {
            return QueueSeverity.WARNING;
        }
        return QueueSeverity.NORMAL;
    }

    boolean changedTo(QueueSeverity next) {
        QueueSeverity before = previous.getAndSet(next);
        return before != next;
    }
}
~~~

This is an example of **transition filtering** inside a single JVM; it does not implement true hysteresis and does not persist across restarts. With multiple queues, state must be maintained **per source ObjectName**, not with a single shared `AtomicReference` for the whole system.

### 12.2. Hysteresis to prevent flapping near thresholds

~~~text
NORMAL → WARNING when Depth >= 80
WARNING → NORMAL when Depth <= 65
WARNING → CRITICAL when Depth >= 120
CRITICAL → WARNING when Depth <= 105
~~~

Hysteresis requires an algorithm based on **previous state** and recovery thresholds, not just `if (depth>=80)`. Choose thresholds based on SLAs, processing capacity, and the cost of false alerts. Rounding numbers alone cannot replace hysteresis.

### 12.3. Cooldown and time windows

For prolonged alerts, you might want a reminder every 15 minutes rather than every 5 seconds. Store `lastAlertAt` and current severity; if an operator has not acknowledged yet, the reminder policy must have limits and escalation tiers. This is alerting business logic, not a built-in feature of the JMX polling adapter.

### 12.4. Multi-instance deployments require durable idempotency

If two Spring replicas poll the same MBean and both detect a transition, local memory will not prevent two notifications from being sent. Use a database unique key, lease/leader election, or an outbox event ID built from source+transition+epoch plus idempotent downstream handling when a single system-wide alert is required.

### 12.5. Using snapshots strictly as gauges

Queue depth is a **point-in-time measurement**. For metrics, updating a gauge is appropriate; do not sum 25+25+25 and call it "75 jobs arrived." To count processed work, the MBean must expose a dedicated counter and handle resets, restarts, and deltas.

## 13. JUnit: testing the JMX reader with an in-process MBeanServer

An advantage of JMX is that you can spin up an `MBeanServer` in the same JVM and test `getAttribute()` without opening a remote JMX port. This is an integration unit test with **real JMX**, not a fixed mock return.

### 13.1. QueueDepthReaderTest.java

~~~java
package demo.jmxpolling;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.management.InstanceNotFoundException;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

class QueueDepthReaderTest {

    private static final String NAME =
            "demo.integration:type=QueueStats,name=Orders";

    @Test
    void readsRegisteredMBeanAttribute() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("demo.test");
        ObjectName name = new ObjectName(NAME);
        QueueStats bean = new QueueStats();
        bean.setDepth(37);

        try {
            server.registerMBean(bean, name);

            QueueDepthReader reader =
                    new QueueDepthReader(server, name);
            QueueDepthSnapshot snapshot = reader.read();

            assertEquals(37, snapshot.depth());
            assertEquals(name.getCanonicalName(),
                    snapshot.objectName());
            assertTrue(snapshot.observedAt() != null);
            assertEquals(Integer.valueOf(37),
                    server.getAttribute(name, "Depth"));
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }

    @Test
    void missingMBeanIsNotSilentlyMappedToZero()
            throws Exception {

        MBeanServer server =
                MBeanServerFactory.createMBeanServer("demo.absent");
        try {
            ObjectName name = new ObjectName(NAME);
            QueueDepthReader reader =
                    new QueueDepthReader(server, name);

            IllegalStateException error = assertThrows(
                    IllegalStateException.class, reader::read);

            assertInstanceOf(
                    InstanceNotFoundException.class,
                    error.getCause());
        } finally {
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
~~~

What the test proves:

1. The Standard MBean is registered and exposes the `Depth` attribute.
2. `getAttribute` reads the exact value set on the bean.
3. The reader normalizes it into a `QueueDepthSnapshot` with ObjectName and timestamp.
4. When the MBean does not exist, the error propagates with a clear cause and does **not** fabricate a `Depth=0` snapshot.

**Limitations:** this test does not run the Spring scheduled adapter, does not use a remote connector, and does not prove queue backlog or durability. It focuses strictly on the JMX reader contract.

### 13.2. Testing attribute name and readability

Extend the test using `server.getMBeanInfo(name)` to verify `MBeanAttributeInfo` contains `Depth` and is readable, then attempt `getAttribute(name, "getDepth")` to observe `AttributeNotFoundException`. This demonstrates the difference between JMX attribute names and Java method names.

### 13.3. Testing null or mismatched data types

If an MBean returns a `String` when the consumer expects an `Integer`, the reader must reject it rather than casting blindly. You can create a separate test MBean exposing `Depth` as a `String` to test the `IllegalArgumentException` branch, or use a fake `MBeanServerConnection` solely for parser tests (without replacing real-server tests).

## 14. JUnit: testing the actual Spring polling endpoint

Unit testing `QueueDepthReader` does not prove the scheduled Spring endpoint runs. With `@SpringJUnitConfig`, you can load `JmxPollingConfiguration` and wait for a snapshot to pass through the channel/flow. Because the poller runs on a schedule, wait with an **explicit timeout** rather than asserting immediately after calling the setter.

### 14.1. JmxPollingFlowTest.java

~~~java
package demo.jmxpolling;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = JmxPollingConfiguration.class)
class JmxPollingFlowTest {

    @Autowired
    QueueStats queueStats;

    @Autowired
    QueueSnapshotSink sink;

    @Test
    void pollsJmxAttributeIntoSpringIntegrationFlow()
            throws InterruptedException {

        queueStats.setDepth(42);

        QueueDepthSnapshot result =
                awaitDepth(42, Duration.ofSeconds(12));

        assertEquals(42, result.depth());
        assertTrue(result.objectName().contains("QueueStats"));
        assertTrue(result.observedAt() != null);
    }

    private QueueDepthSnapshot awaitDepth(
            int expected, Duration timeout)
            throws InterruptedException {

        long deadline = System.nanoTime() + timeout.toNanos();

        while (System.nanoTime() < deadline) {
            for (QueueDepthSnapshot value : sink.snapshot()) {
                if (value.depth() == expected) {
                    return value;
                }
            }
            Thread.sleep(50);
        }

        throw new AssertionError(
                "Did not receive Depth=" + expected
                + " within test timeout");
    }
}
~~~

`Thread.sleep(50)` in this helper only **waits for an asynchronous result up to a 12s deadline**—it is not a substitute for a production poller. You can use `CountDownLatch` or Awaitility if the project has those dependencies. The test is subject to real poller timing; if CI is very slow, adjust the timeout without skipping the business outcome check.

**Isolation concern:** The Spring context has an `MBeanExporter` registering on the JVM's platform `MBeanServer`. If multiple test contexts register the same `ObjectName`, `InstanceAlreadyExistsException` can occur. When running tests in parallel, use per-test ObjectNames or run serially and ensure exporter cleanup on context close.

### 14.2. Testing value changes between polls

At startup, the poller may already have captured the old `Depth`. Tests should filter by `depth==expected` instead of asserting `sink.snapshot().get(0)`. Change `Depth` from 42 → 17 and wait for sample 17 to prove the poller picks up the new value on the next cycle.

### 14.3. Passing the runtime test does not prove every transition is caught

A test receiving `Depth=42` does not mean changes 42 → 100 → 42 between two polls were recorded. That is a **sampling** limitation, not a JUnit or Spring Integration bug.

### 14.4. Testing stop/start lifecycle

An additional integration test can retrieve the Spring polling endpoint bean by its framework-registered ID, call `stop()`, verify no new polls occur after in-flight tasks finish, then call `start()` and verify samples resume. Do not assume stopping the endpoint undoes samples already persisted downstream.

The actual endpoint ID when using `@InboundChannelAdapter` can depend on bean/source names and framework version; fetch the ID from the Spring context or management API rather than hardcoding blindly. If precise stop/start control is needed in tests, configure bean names and endpoint IDs intentionally.

## 15. Remote JMX: connecting to an MBeanServerConnection outside the JVM

`MBeanServerConnection` lets the reader use the same API whether the server is local or remote. For remote JMX, create a `JMXConnector` with secure configuration, obtain the connection, and **close the connector** when the Spring context shuts down.

~~~java
import java.util.Map;

import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

// API illustration pseudocode. Do not expose unsecured remote JMX.
JMXServiceURL url = new JMXServiceURL(
        "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi");

Map<String, ?> environment = Map.of(
        JMXConnector.CREDENTIALS,
        new String[] { "monitor-user", "demo-only-not-a-secret" });

JMXConnector connector =
        JMXConnectorFactory.connect(url, environment);

MBeanServerConnection remote =
        connector.getMBeanServerConnection();

// QueueDepthReader reader = new QueueDepthReader(remote, name);
// On shutdown/connection recreation: connector.close().
~~~

**Do not copy hardcoded credentials to production.** The snippet above only illustrates the API with placeholder user/password values. In real systems, load secrets from a protected vault/config, enforce TLS/certificate verification, least privilege, and proper RMI port/hostname/firewall settings. If remote JMX is not required, the in-JVM platform server is simpler and safer.

### 15.1. Remote polls can block longer than the interval

A `getAttribute` call over RMI depends on network latency and remote JVM load. If a timeout exceeds 5 seconds, a 5-second fixed-delay poll will no longer produce samples every 5 seconds. Monitor latency, timeouts, missed samples, and backpressure—not just scheduled task counts.

### 15.2. Reconnect does not recover historical values

After a connector loses network connectivity for 30 seconds, the next read only fetches the current attribute. Peaks and transitions during those 30 seconds may be gone; JMX attribute polling does not keep a snapshot backlog.

### 15.3. Remote JMX security checklist

- Never expose unauthenticated JMX/RMI publicly.
- Require TLS and verify certificate/host identity; firewall/allowlist management networks.
- Use credentials with **read** permission only on required MBeans; avoid granting access to dangerous operations.
- Never log usernames/passwords, tokens, or sensitive raw `userData`.
- Manage connector lifecycle, stale references, and reconnect backoff.
- Be cautious with remote JMX Java serialization/deserialization to avoid loading untrusted object classes.
- Restrict which MBeans may actually be read and validate payload types in the application.

### 15.4. Local and remote MBeans can share an ObjectName yet have different identities

`demo.integration:type=QueueStats,name=Orders` on JVM A is distinct from the same-named MBean on JVM B. When writing to metrics or an outbox, identity must include **server/cluster/node** or a trusted assigned source ID, not just the `ObjectName` string.


## 16. Lifecycle: MBean registration vs. the polling endpoint

MBeans are registered/unregistered with the JMX server by `MBeanExporter`, whereas a Spring `@InboundChannelAdapter` or XML polling endpoint has its own start/stop lifecycle.

~~~mermaid
sequenceDiagram
    participant CT as Spring Context
    participant EXP as MBeanExporter
    participant MB as MBeanServer
    participant POLL as Polling Endpoint
    participant CH as MessageChannel
    CT->>EXP: Create QueueStats
    EXP->>MB: registerMBean(ObjectName)
    CT->>POLL: Start
    POLL->>MB: getAttribute("Depth")
    MB-->>POLL: Integer value
    POLL->>CH: Message<snapshot>
    CT->>POLL: Stop
    CT->>EXP: Unregister on close
~~~

### 16.1. A running endpoint does not guarantee values can be read

If the MBean has not been exported, the `ObjectName` is wrong, or remote JMX is down, the Spring poller may be RUNNING while every `getAttribute()` fails. Readiness must observe the most recent successful read, not just `isRunning()`.

### 16.2. MBean unregistered at runtime

The next read may throw `InstanceNotFoundException`. If the MBean re-registers under the same name, the reader may resume working, but you must verify the new attribute type/schema. Never replace null/exceptions with a `Depth=0` snapshot, as that misleads operators into thinking the queue is empty.

### 16.3. Stopping the poller does not remove the MBean

Stopping the Spring polling endpoint halts sampling, while the platform `MBeanServer` and source MBean can keep running. On context close, `MBeanExporter` should unregister the MBeans it manages; do not destroy the entire platform server.

### 16.4. Startup ordering and shutdown

The poller may be scheduled before MBean registration completes in complex systems. Test startup/lifecycle, configure bounded retries or explicit dependencies/readiness. At shutdown, track in-flight remote JMX calls; stopping does not roll back a snapshot already written to a DB.

## 17. Backpressure and polling cost

~~~mermaid
flowchart LR
    P["Poller tick"]
    READ["JMX getAttribute"]
    CH["DirectChannel"]
    SLOW["Slow HTTP/DB handler"]
    P --> READ --> CH --> SLOW
~~~

If the downstream handler runs synchronously and takes 20 seconds, a 5-second poll interval cannot maintain a 5-second sampling cadence. Even when the scheduler keeps ticking, blocked executors and queue backlogs lead to stale data.

### 17.1. Cost by number of sources and frequency

If 200 MBeans are each polled once per second, the application performs roughly **200 JMX reads/s**, excluding retries, metadata discovery, or additional converters. Remote JMX adds network/RMI/serialization overhead; measure p50/p95/p99 latency and CPU/GC on the source JVM.

### 17.2. ExecutorChannel does not create durability

You can use a bounded `ExecutorChannel` or `QueueChannel` to decouple the poller from a slow handler. However:

- Threads and queue capacity must be bounded;
- Define an overflow policy (reject, backpressure, drop stale);
- Provide an error channel for asynchronous handler failures;
- Implement shutdown draining with a timeout;
- Never treat an in-memory buffer as a durable message broker.

For "latest value" gauges, dropping stale snapshots can be preferable to processing hours of backlog. For critical audits, you need a durable inbox/outbox or an event stream at the source.

### 17.3. max-messages-per-poll is not the number of attributes

`max-messages-per-poll=1000` on an attribute source can read **the same value repeatedly** within one poll task rather than returning 1,000 different attributes. For a single-attribute source that always yields a value, `1` is clearer and avoids wasted MBean calls.

### 17.4. Sampling cannot be fixed by adding more workers

More threads or a tighter fixed-rate can increase sampling resolution, but cannot capture transitions that were never observed. If every occurrence is required, choose a notification/event publisher or a source that maintains history.

## 18. Forwarding JMX snapshots to other adapters

Once a snapshot is on a Spring `MessageChannel`, the flow can continue using transformers/routers and database, HTTP, JMS, AMQP, Kafka, file, or SFTP adapters.

~~~mermaid
flowchart LR
    JMX["JMX Polling"]
    CH["MessageChannel"]
    DTO["Normalize Snapshot"]
    FILT["Filter/State Transition"]
    DB[("DB + Outbox")]
    RELAY["Relay"]
    DEST["HTTP / Kafka / JMS / SFTP"]
    JMX --> CH --> DTO --> FILT --> DB --> RELAY --> DEST
~~~

### 18.1. Database and time-series

Store `objectName`, `attributeName`, `value`, and `observedAt` along with namespace/node ID. If the goal is simply displaying the latest gauge, upserting one row suffices; for trend analysis, plan time-series sampling and retention. Never sum each `Depth` snapshot as a work counter.

### 18.2. HTTP outbound

An HTTP timeout does not always prove the target server did not receive the snapshot. If retries are needed, use an idempotency key and target contract. If only updating current state, you can use PUT/upsert by source+attribute, accepting latest-value semantics rather than historical events.

### 18.3. Kafka/JMS/AMQP

When durable forwarding is required, write an outbox event within a database transaction and relay it to the message broker. Because the relay could publish successfully and crash before marking it sent, downstream also needs idempotency. Do not advertise JMX attribute polling as end-to-end exactly-once: the source does not replay missed snapshots.

### 18.4. File/SFTP

To export snapshots as CSV/JSON, choose collision-free filenames, use temp-write + rename where supported, and plan retention and reconciliation on upload timeouts. When polling frequently, do not generate unbounded tiny files without lifecycle management. For time-series data, use explicit batching or rolling windows.

### 18.5. Missed spikes cannot be reconstructed

If queue depth jumps to 100 for 200ms while the poller runs once every 5 seconds, even a durable downstream Kafka cluster **cannot reconstruct a value that was never polled**. To capture that event, the MBean must emit a Notification or expose an aggregate such as `maxSinceLastPoll`.

## 19. Securing local and remote JMX

### 19.1. Least privilege

Attribute polling only needs to **read** specific attributes. Do not grant permissions to invoke JMX operations or write attributes unless required. MBeans can expose sensitive JVM configuration; enforce an `ObjectName`+attribute allowlist and control which components may connect.

### 19.2. Remote connector

- Use TLS/mTLS or proper authentication and verify hostnames/certificates.
- Never expose unprotected remote JMX/RMI to the Internet.
- Verify RMI hostname, registry port, connection port, and firewall/container networking.
- Load secrets from a secure environment/vault; never hardcode or log them.
- Restrict remote accounts to reading only the required attributes.
- Manage `JMXConnector.close()` and reconnect/backoff on connection loss.
- Be cautious of Java serialization/deserialization and untrusted remote classes/`userData`.

### 19.3. ObjectName must not be built from arbitrary input

If tenant/device IDs come from an HTTP request, validate and quote key property values according to JMX `ObjectName` rules. Do not let callers pick `java.lang:*` or read the entire `MBeanServer` simply by changing a query string; read access must be enforced by the service.

### 19.4. Do not log every raw attribute

An MBean might expose JDBC URLs, usernames, or secrets; dumping raw values to logs/HTTP/Kafka can leak sensitive information. Maintain an allowlist of safe attributes, redact where needed, and limit retention.

## 20. Observability for poller, reader, and downstream

| Recommended metric | Meaning |
| --- | --- |
| `jmx_attribute_poll_attempts_total` | Number of read attempts. |
| `jmx_attribute_poll_success_total` | Number of successful reads. |
| `jmx_attribute_poll_errors_total{kind}` | Breakdown of absent MBean, IO, schema, permission errors. |
| `jmx_attribute_poll_duration_seconds` | Duration of `getAttribute`/conversion. |
| `jmx_attribute_last_success_epoch_seconds` | Detects stale sources. |
| `jmx_attribute_snapshot_age_seconds` | Age of the latest snapshot. |
| `jmx_mbean_registered{source}` | Whether the `ObjectName` exists and is readable. |
| `jmx_remote_connection_up` | Health of remote JMX connection. |
| `spring_jmx_channel_errors_total` | Errors dispatching from source to channel. |
| `jmx_snapshot_dropped_total{reason}` | Samples dropped by policy. |
| `jmx_alert_transitions_total{severity}` | Number of actual severity transitions. |
| `outbox_backlog_count` | Durable backlog awaiting relay. |

These are **suggested metric names**; Spring Integration JMX does not automatically emit all of these by default. Do not use individual ObjectNames, devices, or sample timestamps as high-cardinality metric labels; use access-controlled logs/traces for fine-grained debugging.

### 20.1. Trace of a normal poll

~~~text
12:00:00 POLL_TRIGGERED source=orders
12:00:00 JMX_READ Depth=42
12:00:00 SNAPSHOT_NORMALIZED
12:00:00 CHANNEL_DISPATCHED
12:00:00 GAUGE_UPDATED
~~~

Trace on remote failure:

~~~text
12:00:05 POLL_TRIGGERED
12:00:07 JMX_READ_FAILED kind=IOException
12:00:07 SOURCE_STALE / next poll scheduled
~~~

Never silently record `Depth=0` when a read fails. "Unknown/stale" and an actual value of 0 mean two completely different things.

### 20.2. Readiness is more than the endpoint being RUNNING

Alert if 2–3 consecutive intervals pass without a valid sample, or if sample age exceeds the SLA. A RUNNING poller hitting `InstanceNotFoundException` on every tick is still a broken source; monitor connectivity, `ObjectName`, last-success, and downstream backlog.


## 21. Symptom-based troubleshooting

| Symptom | First check | Resolution |
| --- | --- | --- |
| Adapter starts but no messages arrive | Is MBean registered? Is poller configured? Does channel have a consumer? | Verify bean name, `ObjectName`, attribute, endpoint lifecycle, and error logs. |
| Repeated `InstanceNotFoundException` | Wrong `ObjectName` or source not exported yet. | Check `mbeanServer.isRegistered(...)` and startup ordering. |
| `AttributeNotFoundException` | Wrong attribute name or case. | Inspect `MBeanInfo.getAttributes()`; use `Depth` instead of `getDepth`. |
| Value always 0 despite queued items | Reader falls back to 0 on exception, or reads the wrong `MBeanServer`. | Do not swallow exceptions; verify server/identity. |
| JConsole sees attribute but app cannot read it | Possibly two different `MBeanServer`s or remote endpoints. | Check the actual `MBeanServerConnection` in use. |
| Receiving many identical messages | Repeated snapshots from poller, or two endpoints polling the same source. | Gauge vs. transition filter; check for duplicate configurations. |
| Alert emails sent every 5 seconds | Predicate only checks threshold without tracking state. | Add stateful detector/hysteresis/cooldown. |
| Very brief spikes missed | Changes happened between two polls. | Use JMX notifications, `maxSinceLastPoll`, or an event stream. |
| `ClassCastException` on `HeapMemoryUsage` | Value is `CompositeData`. | Use `MemoryUsage.from(...)` or a converter. |
| Spring `@InboundChannelAdapter` does not emit | Missing `@EnableIntegration`, misconfigured source/channel, or bean not scanned. | Check Spring context wiring and integration endpoint. |
| Scheduled test fails intermittently | Asserting before the poller runs. | Use bounded await, adjust test timeout, and isolate tests. |
| CI reports `ObjectName` already registered | Two test contexts share the platform `MBeanServer`/`ObjectName`. | Use unique ObjectNames, exporter cleanup, or serial tests. |
| Remote JMX `IOException` | RMI network, firewall, TLS, or server restart. | Reconnect/backoff, track gaps, verify connector config. |
| High poller latency | Blocking getter or slow handler on `DirectChannel`. | Measure each stage; use bounded executor and reasonable sampling interval. |
| `QueueChannel` fills up | Producer faster than consumer without backpressure. | Bound buffers; drop stale or persist per SLA. |
| Error channel receives no errors | Polling endpoint/handler error path differs from assumptions. | Test on exact framework version and configure error flow explicitly. |
| Re-registered MBean has different attribute type | New source broke the old contract. | Validate schema/type/version, quarantine, and alert operators. |
| Dashboard reports 0 right when remote disconnects | App substitutes 0 on error. | Switch to UNKNOWN/STALE and preserve last-known value separately. |

### 21.1. Check JMX attributes with the Java API before debugging IntegrationFlow

~~~java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
        "demo.integration:type=QueueStats,name=Orders");

boolean registered = mbeanServer.isRegistered(name);
System.out.println("MBean registered: " + registered);

if (registered) {
    Object value = mbeanServer.getAttribute(name, "Depth");
    System.out.println("Depth type: "
            + (value == null ? "null" : value.getClass().getName()));
    System.out.println("Depth value: " + value);
}
~~~

If the attribute cannot be read from `MBeanServer`, the issue is in JMX/object name/source rather than Spring transforms or routers. If JMX reads succeed but the channel receives nothing, inspect poller scheduling, endpoint running state, error channel, and output channel.

### 21.2. Observing handlers in the lab

A `DepthLogHandler` logging each snapshot helps verify the flow, but do not keep high-frequency per-snapshot logging in production across thousands of MBeans. Track aggregate metrics, sample age, and threshold transitions instead of unbounded raw logging.

### 21.3. Do not use Thread.sleep in production to build a poll loop

Spring Integration already provides `@Poller` and XML pollers. Building `while(true)` + `Thread.sleep(5000)` in a custom service makes lifecycle, shutdown, error handling, and concurrency hard to control. In JUnit, a short sleep may serve as a **bounded wait** to observe the scheduler, which is completely different from production loop scheduling.

## 22. Anti-patterns and fixes

| Anti-pattern | Why it is wrong | Alternative |
| --- | --- | --- |
| Using notification-listening adapter for a getter-only MBean. | Source does not emit `Notification`s. | Attribute polling adapter with a poller. |
| Omitting the poller from an attribute adapter. | No proactive trigger to read. | Configure `<int:poller>` or `@Poller`. |
| Using `attribute-name="getDepth"`. | Getter method differs from JMX attribute name. | `attribute-name="Depth"`. |
| Using an `ObjectName` pattern as a single attribute read. | `getAttribute` requires a concrete MBean. | Exact `ObjectName`; query/aggregate for multiple MBeans. |
| Summing snapshots as "number of events that occurred." | Snapshots are not event occurrences. | Gauge or counter with accurate semantics. |
| Polling every 5s while promising to catch every 100ms spike. | Sampling misses transitions between polls. | Notification/history/event source. |
| Sending an email on every poll above threshold. | Alert spam while state stays unchanged. | Hysteresis/stateful change detection. |
| Casting raw `HeapMemoryUsage` to `Long`. | MXBeans typically return `CompositeData`. | Map OpenType with a converter/schema. |
| Returning `Depth=0` when getter fails. | Masks outages and creates false reports. | UNKNOWN/STALE + error metric. |
| Setting `maxMessagesPerPoll` very high for one attribute. | Reads the same value repeatedly in one task. | `1`, or configure per source contract. |
| Sharing one mutable state across all queues. | Alert transitions mix across sources. | Key state by source `ObjectName`/node. |
| Treating JMX Client ID like MQTT Client ID. | JMX lacks MQTT client subscription semantics. | Separate identity by protocol; use `ObjectName`/connector. |
| Calling remote JMX without TLS/auth. | Exposes JVM management. | TLS, auth, firewall, least privilege. |
| Treating in-memory `ExecutorChannel` as a durable queue. | Messages are lost on crash if not persisted. | Durable inbox/outbox when required. |
| Serializing `CompositeData` straight to JSON without mapping. | Unstable schema and fragile serialization. | Versioned DTO with primitive fields. |
| Assuming Kafka send + DB mark-sent are atomic. | Two systems do not share a transaction. | Outbox + idempotent downstream. |
| Accidentally running XML and Java endpoints on the same MBean. | Double sampling and duplicate alerts. | Single owner and explicit endpoint ID metrics. |
| Equating `observedAt` with when the queue changed. | Snapshots only know sampling time. | Add change timestamp/event contract at the source. |

## 23. Hands-on exercise: multi-queue monitoring with JMX

**Scenario:** An order-processing system has queues `Orders`, `Billing`, and `Notifications`. Each queue exposes a Standard MBean with `Depth` and `Healthy`; the system needs to sample depth every 5 seconds, display gauges, alert on overload, and save summaries to a database.

### 23.1. Implementation requirements

1. Define `QueueStatsMBean` and `QueueStats`, exposing `Depth`, `Healthy`, and a test operation.
2. Register the MBeans via `MBeanExporter` with ObjectNames:
   - `demo.integration:type=QueueStats,name=Orders`
   - `demo.integration:type=QueueStats,name=Billing`
   - `demo.integration:type=QueueStats,name=Notifications`.
3. Write a native XML `int-jmx:attribute-polling-channel-adapter` for at least one source, polling every 5 seconds with `<int:poller>`.
4. For the remaining sources, configure separate adapters per `ObjectName` or build a Java source with an explicit list of MBeans; do not pass an `ObjectName` pattern to `getAttribute` expecting multiple values automatically.
5. Set `max-messages-per-poll=1` for each attribute source and explain why.
6. Use Java `@InboundChannelAdapter`/`MessageSource` for a case requiring the `QueueDepthSnapshot` DTO.
7. Map the `Integer` payload and headers/source identity to a JSON schema: `source,attribute,value,observedAt,schemaVersion`.
8. Implement a JUnit test directly against a local `MBeanServer`, asserting `Depth`/`Healthy` names and types.
9. Implement a Spring polling test using bounded await, verifying new values reach the flow after `setDepth`.
10. Test `AttributeNotFoundException`, an unregistered MBean, and runtime unregister/re-register of the source.
11. Test `Depth` staying unchanged for 3 cycles: update the gauge without sending 3 alerts.
12. Build NORMAL/WARNING/CRITICAL state tracking with hysteresis and cooldown, isolated per queue.
13. Simulate a queue spiking to 200 and dropping back to 0 between two polls, and explain why snapshots cannot claim to have caught the spike.
14. Add `java.lang:type=Memory`, read `HeapMemoryUsage`, and convert `CompositeData` to bytes.
15. Integrate a downstream JMS/AMQP/Kafka/HTTP gateway via the DTO with appropriate retry/idempotency/outbox policies.
16. Slow down the downstream handler by 10 seconds, measure poll lag/backpressure, and compare `DirectChannel` vs. bounded executor.
17. Test remote JMX in an isolated lab with TLS/auth enabled, verifying connector disconnect/reconnect.
18. Create a dashboard for poll success/errors, last-success age, sample latency, and alert transitions.
19. Verify that stopping/starting the endpoint does not delete the MBean or roll back business writes.
20. Compare attribute polling with JMX notification listening and decide which tool fits "measure current state" vs. "never miss any transition."

### 23.2. Acceptance criteria

- Reads a JMX attribute accurately by concrete `ObjectName`; distinguishes attributes from Java getters.
- Spring Poller and `MessageChannel` run properly, using native XML or a Java bridge accurately described as such.
- Snapshot DTO includes source/time/value and a valid schema; polls are not treated as change events.
- Read errors are not converted into fake `0` values; appropriate retry/alerting is in place.
- Thresholds do not cause alert storms and are scoped per source.
- Both local JMX and Spring polling tests have deadlines and cleanup.
- Sampling limits, durability, remote security, and backpressure are accurately explained.

### 23.3. Exercise extension: multi-source health monitoring

Design a `HealthSnapshot` containing `nodeId`, `objectName`, `attribute`, `value`, `observedAt`, and `quality`. If the last successful read was at 12:00:00 and the next three cycles lose remote JMX, store `quality=STALE` or `UNKNOWN` rather than writing 0. Once the connector recovers, update with the new snapshot; do not fabricate "state history" for unmeasured intervals.

## 24. Self-check questions

1. Is the JMX attribute-polling adapter an inbound or outbound endpoint?
2. Which API does the adapter actively call to retrieve the value?
3. Why does it require a poller while the notification-listening adapter does not?
4. What JMX attribute name does `QueueStats.getDepth()` produce?
5. Is `resetCounters()` a JMX attribute or an operation?
6. How do `MBeanServer` and `MBeanServerConnection` differ?
7. Is `ObjectName` the same as a Spring bean name or `MessageChannel` ID?
8. If `attribute-name` has the wrong capitalization, which exception can occur?
9. How does `MBeanInfo` help debug a missing attribute?
10. What data type does JMX `MemoryMXBean`'s `HeapMemoryUsage` typically return?
11. Does `MemoryUsage.getUsed()` use bytes or MiB?
12. When `getMax() == -1`, should you compute `used/max`?
13. How does `fixed-delay` differ from `fixed-rate`?
14. Does `max-messages-per-poll=1000` mean reading 1,000 different attributes?
15. Why are three polls returning `Depth=25` not three queue changes?
16. Is a spike shorter than the poll interval guaranteed to be seen?
17. Is `observedAt` the true timestamp when the value changed?
18. When an MBean is not yet registered, why must you not return `Depth=0` by default?
19. If the 12:00:05 poll fails and the 12:00:10 poll succeeds, does it replay the lost snapshot?
20. In the Java bridge, what are the roles of `@InboundChannelAdapter` and `MessageSource<?>`?
21. Is a custom Java reader calling `getAttribute` the same class as the native `AttributePollingMessageSource`?
22. How do the lifecycles of `MBeanExporter` and a Spring polling endpoint differ?
23. Why does remote JMX require TLS, authentication, and firewalling?
24. When two remote JVMs share the same `ObjectName`, what extra identifier is needed?
25. What problem can a `DirectChannel` with a slow HTTP handler cause for the scheduler?
26. Does `ExecutorChannel` make messages durable across restarts?
27. When alerting on `Depth≥80`, how do you avoid sending emails every 5 seconds?
28. How does hysteresis differ from a simple threshold filter?
29. To forward snapshots to Kafka reliably, why are an outbox and downstream idempotency needed?
30. How does a bounded JUnit await differ from a production loop using `Thread.sleep`?
31. When a Spring polling endpoint is RUNNING yet the source is broken, what metrics are needed?
32. When every single queue transition is required, what tool/architecture should you switch to?

**Hint:** JMX attribute polling always answers "the state at read time," not "every event that happened." Choose polling intervals, schemas, error policies, and downstream guarantees according to the actual SLA.

## 25. Conclusion and references

The **JMX attribute-polling adapter** bridges JVM management JMX into Spring Integration:

- **JMX `MBeanServerConnection.getAttribute`** reads a snapshot of a named attribute on a concrete `ObjectName`.
- **Native Spring Integration `int-jmx:attribute-polling-channel-adapter`** creates an inbound endpoint with a poller, channel, and explicit JMX metadata.
- **Java `@InboundChannelAdapter` + `MessageSource`** is an approach for building a custom bridge that packages DTO/source/timestamp, though it must be distinguished from the native JMX source implementation.
- **Polling is not notification:** repeated values are not an error, and transitions occurring between polls can be missed.
- **`CompositeData`/OpenType** values must be normalized before sending to HTTP/JMS/AMQP/Kafka/file/SFTP.
- **Lifecycle, error handling, backpressure, and security** determine source reliability, especially for remote JMX.
- **Durable delivery and idempotency** are not provided natively by JMX polling; critical business events require an event source and an appropriate inbox/outbox or broker.

In the **SPRING_INTEGRATION_ADAPTERS** module, this lesson demonstrates connecting **JMX attribute → Spring Poller → MessageChannel → IntegrationFlow → downstream adapter**. By understanding the difference between **snapshot sampling** and **event processing**, learners can build effective monitoring flows without claiming "zero event loss" guarantees when the source never recorded those events.

### 25.1. Reference documentation for version verification

- [Spring Integration Reference – JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html): JMX adapters, attribute polling, notification listening, and XML namespace.
- [Spring Integration Reference – Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html): poller mechanics, fixed-delay, fixed-rate, and endpoints.
- [Java 17 JMX API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/package-summary.html): `MBeanServer`, `MBeanServerConnection`, `ObjectName`, and JMX exception types.
- [Java MemoryUsage](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html): heap memory information and max-value rules.

**STEP 4 note:** The examples in this lesson are Knowledge materials for learning and technical discussion. When applying them to a real project, verify dependencies/XSDs/APIs against your application version and run integration tests. Intensive Content QA/refactoring belongs to STEP 6, not the STEP 4 authoring task.


