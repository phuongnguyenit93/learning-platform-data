# JMX tree-polling adapter

## 1. Goal: capturing a snapshot of multiple MBeans via Spring Integration

A Java application manages several queues: `Orders`, `Billing`, and `Notifications`. Each queue exposes a Standard MBean containing `Depth` and `Healthy` attributes. The monitoring system needs to periodically read **all queue MBeans matching a pattern**, without creating a separate endpoint per queue, and push the combined snapshot into Spring Integration to build a dashboard, send alerts, or export JSON to another service.

The **JMX tree-polling adapter** solves this problem. It queries the **JMX MBean tree** using an `ObjectName` pattern/`QueryExp`, converts each selected MBean and its chosen attributes into an **object graph** of simple types such as `Map`, `List`, arrays, or primitives, and then emits **a single Spring Message containing the snapshot** onto a `MessageChannel` on a Spring Integration poller schedule.

The lesson **“JMX tree-polling adapter”** belongs to the **Adapter JMX** chapter, **SPRING_INTEGRATION_ADAPTERS** module. This module covers connecting external systems through inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing file, SFTP, HTTP, JMS, AMQP, Kafka, and database exchange; and handling message contracts, errors, and connection lifecycles. In that chain, JMX is a source of JVM management data, while tree polling is an inbound endpoint that turns a set of JMX states into a Spring message processed just like any other source.

After this lesson, the reader will be able to:

1. Distinguish **JMX attribute polling** of a single MBean from **tree polling** querying multiple MBeans, and from **notification listening**.
2. Understand `MBeanServerConnection`, `ObjectName` query patterns, `query-name`, optional `QueryExp`, and MBean metadata.
3. Configure the native `int-jmx:tree-polling-channel-adapter`, `mbean-server`, `converter`, `MessageChannel`, and poller.
4. Use `MBeanTreePollingMessageSource` in Java DSL/`@InboundChannelAdapter` together with `DefaultMBeanObjectConverter`.
5. Use `NamedFieldsMBeanAttributeFilter` and `NotNamedFieldsMBeanAttributeFilter` to filter attributes before the converter reads data.
6. Build an example with multiple Standard MBeans, query by wildcard, receive the snapshot in an `IntegrationFlow`, and normalize the payload.
7. Understand the limits of "one snapshot" vs. "a change event," handling dynamic MBeans, partial failures, OpenType, and JSON.
8. Write real JMX tests in the same JVM, test Spring flows/pollers, and design integration tests for remote JMX.
9. Identify security controls, polling cost, threading/backpressure, metrics, retries, and durable downstream handoff.
10. Choose between tree polling, attribute polling, JMX notification listening, and a message broker based on real requirements.

**Foundational message:** tree polling is not a JMX event stream. It is **sampling**: "At the time of polling, what states do the MBeans matching the query have?" If a state changes and reverts between two samples, the snapshot may not reflect that event.

## 2. Architecture: source → snapshot → MessageChannel → downstream

~~~mermaid
flowchart LR
    M1["QueueStats MBean<br/>Orders"]
    M2["QueueStats MBean<br/>Billing"]
    M3["QueueStats MBean<br/>Notifications"]
    SERVER[("JMX MBeanServer")]
    POLLER["Spring Poller<br/>fixed-delay=5s"]
    SOURCE["MBeanTreePollingMessageSource<br/>query-name pattern"]
    CONV["MBeanObjectConverter<br/>filter attributes"]
    CH["jmx.tree.snapshots<br/>MessageChannel"]
    FLOW["IntegrationFlow<br/>validate/normalize/route"]
    DB[("Metrics / DB / outbox")]
    EXT["HTTP / JMS / AMQP / Kafka / SFTP"]
    M1 --> SERVER
    M2 --> SERVER
    M3 --> SERVER
    POLLER --> SOURCE
    SOURCE -->|"queryNames / inspect"| SERVER
    SOURCE --> CONV
    CONV -->|"Message<graph>"| CH --> FLOW --> DB
    FLOW --> EXT
~~~

A cycle consists of:

1. The poller triggers and invokes `MBeanTreePollingMessageSource.receive()`.
2. The source uses `MBeanServerConnection` to query MBeans matching `query-name` (and `query-expression` if configured).
3. For each selected MBean, `MBeanObjectConverter` extracts/transforms MBean information according to `MBeanAttributeFilter`.
4. The framework builds an **object graph** composed of simple objects such as `Map`, `List`, arrays, and primitives/strings; the graph is not automatically an application-defined DTO class.
5. The poller emits a Spring message to the output channel; the flow receives the **entire snapshot** rather than automatically emitting each attribute as a separate message.
6. The flow normalizes and routes it to metrics, a database, or downstream adapters according to application schemas and policies.
7. The next poll re-queries the current set of MBeans; if MBeans appear or disappear, the snapshot content can change.

**Responsibility boundaries:** JMX manages MBeans and attribute access; the Spring poller controls the cadence; the converter controls data representation and filtering; `IntegrationFlow` enforces data contracts and business logic; downstream owns its own durability.

### 2.1. A snapshot every 5 seconds does not equal 5 seconds of full history

~~~text
12:00:00 → {Orders=12, Billing=3}
12:00:05 → {Orders=20, Billing=4}
12:00:10 → {Orders=15, Billing=2, Notifications=9}
~~~

If `Orders` climbs from 12 to 500 and drops back to 20 between 12:00:00 and 12:00:05, tree polling can miss the 500 peak. If `Notifications` is newly registered before the 12:00:10 poll, it can appear in the next snapshot; inspect your actual source query and lifecycle carefully.

### 2.2. A single source can read many attributes in one poll

Tree polling differs from attribute polling in that a single `receive()` can traverse many MBeans and many attributes. If the filter is too broad, one poll can perform many JMX reads and build a huge object graph. Restrict `query-name` and the attribute filter **up front** rather than reading the entire JVM and filtering downstream.

## 3. JMX fundamentals for tree queries

### 3.1. MBean, MBeanServerConnection, and ObjectInstance

- **MBean**: a Java component exposing managed attributes and operations; for example, `QueueStats` has `Depth` and `Healthy`.
- **MBeanServer**: manages the registry inside the JVM; can be obtained via `ManagementFactory.getPlatformMBeanServer()`.
- **MBeanServerConnection**: interface for interacting with a local or remote JMX server, used for `queryNames`, `queryMBeans`, `getMBeanInfo`, and `getAttribute`.
- **ObjectName**: JMX identifier consisting of a domain and key properties, e.g., `demo.integration:type=QueueStats,name=Orders`.
- **ObjectInstance**: a discovered MBean, containing its `ObjectName` and JMX class name.
- **QueryExp**: JMX query expression for adding predicates beyond the name pattern when needed.
- **MBeanAttributeInfo**: attribute metadata from `MBeanInfo`, including name, type, and read/write access.

These concepts are not Spring `MessageHeaders`, Kafka topics, or MQTT client IDs. JMX object names and Spring bean/channel IDs are two independent namespaces.

### 3.2. ObjectName patterns and query-name

Pattern to select three queue instances:

~~~text
demo.integration:type=QueueStats,name=Orders
demo.integration:type=QueueStats,name=Billing
demo.integration:type=QueueStats,name=Notifications

Pattern:
demo.integration:type=QueueStats,name=*
~~~

The pattern is used in **`query-name`** for tree polling. It differs from `object-name` on the single attribute-polling adapter, which reads one concrete MBean.

~~~java
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        java.lang.management.ManagementFactory.getPlatformMBeanServer();

ObjectName filter = new ObjectName(
        "demo.integration:type=QueueStats,name=*");

var matches = server.queryNames(filter, null);

for (ObjectName match : matches) {
    System.out.println(match.getCanonicalName());
}
~~~

An `ObjectName` pattern can match multiple MBeans; a concrete `ObjectName` matches only one. Query patterns should be narrow, favoring managed domains/types/tenants, and never letting untrusted HTTP clients choose `*:*` queries across the whole JVM.

### 3.3. query-name vs. query-expression

| Concept | JMX type | Purpose |
| --- | --- | --- |
| `query-name` | `ObjectName` pattern, typically written as a string in XML. | Selects MBeans with matching domain/key properties. |
| `query-expression` | `QueryExp`/expression supported by the source. | Further filters using JMX query conditions (if needed). |
| Attribute filter | `MBeanAttributeFilter`. | Decides which attributes are read and placed into the graph. |
| Spring `.filter(...)` | Predicate inside `IntegrationFlow`. | Filters the **snapshot message** after the source has already read it. |

Do not confuse `query-name`, which finds **MBeans**, with `NamedFieldsMBeanAttributeFilter`, which selects **attributes** of the matched MBeans.

### 3.4. A readable attribute can have an expensive getter

JMX attributes are MBean code. `getDepth()` might only read an `AtomicInteger`, whereas getters in some libraries perform I/O, locking, or heavy statistics computation. Tree polling across many MBeans and attributes multiplies getter cost. And over remote JMX, it is not a free network call.

### 3.5. JMX OpenType: CompositeData and TabularData

MXBeans can expose `CompositeData`, `TabularData`, arrays, or complex structures. The default converter attempts to translate MBean values into simple structures (`Map`/`List`/arrays) according to supported semantics, yet downstream must still validate the actual object graph and never assume every custom Java class serializes safely to JSON.

## 4. Comparing tree polling with other JMX adapters

| Endpoint | Trigger | Target read | Typical payload | When to use |
| --- | --- | --- | --- | --- |
| JMX attribute-polling inbound | Poller | One attribute on a concrete MBean. | Single value: `Integer`, `String`, `CompositeData`. | Need a gauge/health value from one clear source. |
| JMX tree-polling inbound | Poller | MBeans matching query and selected attributes. | Graph of primitives, `Map`, `List`, arrays. | Multi-MBean inventory/snapshot dashboard. |
| JMX notification-listening inbound | Listener callback | Notifications proactively emitted by an MBean. | `javax.management.Notification`. | Need events/transitions close to when they happen. |
| JMX operation-invoking outbound | Spring message | Calls an operation on an MBean. | Not necessarily a reply. | Executing management/control actions. |
| JMX operation-invoking gateway | Request-reply | Calls an operation and returns result. | Reply message from the operation. | Need the return value of a management command. |
| JMS/AMQP/Kafka inbound | Broker/stream | Stored messages/records. | Domain message/record. | Want durability, retry/replay, and consumer coordination. |

**Do not use tree polling to promise catching every change**, as it is primarily for **state scanning**; if the goal is zero lost business events, you need an event source and durable infrastructure.

## 5. XML namespace: native tree-polling channel adapter

Spring Integration provides the native endpoint `int-jmx:tree-polling-channel-adapter`.

~~~xml
<int-jmx:tree-polling-channel-adapter
        id="queueTreeAdapter"
        channel="jmxTreeSnapshots"
        query-name="demo.integration:type=QueueStats,name=*">
    <int:poller max-messages-per-poll="1"
                fixed-rate="5000"/>
</int-jmx:tree-polling-channel-adapter>
~~~

This is the official native form: `query-name` is the JMX `ObjectName` pattern, `channel` is the Spring output `MessageChannel`, and the nested poller sets a 5,000-millisecond cadence. If the context has a bean named `mbeanServer`, the adapter can locate it by that name. To use a different server, configure `mbean-server` explicitly.

### 5.1. Complete XML wiring configuration

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

    <int:channel id="jmxTreeSnapshots"/>

    <int-jmx:tree-polling-channel-adapter
            id="queueTreeAdapter"
            channel="jmxTreeSnapshots"
            mbean-server="mbeanServer"
            query-name="demo.integration:type=QueueStats,name=*">
        <int:poller max-messages-per-poll="1"
                    fixed-delay="5000"/>
    </int-jmx:tree-polling-channel-adapter>

    <bean id="treeLogHandler"
          class="demo.jmxtree.TreeLogHandler"/>

    <int:service-activator
            input-channel="jmxTreeSnapshots"
            ref="treeLogHandler"
            method="handle"/>
</beans>
~~~

The XML creates the `MBeanServer` and Spring channel/endpoint/handler; it **does not automatically generate the three `QueueStats` MBeans**. Publisher MBeans must be registered on the same server under the corresponding names; section 10 creates them with `MBeanExporter`.

### 5.2. Simple handler for the XML example

~~~java
package demo.jmxtree;

public class TreeLogHandler {

    public void handle(Object treeSnapshot) {
        // Lab only: log restricted metadata.
        System.out.println("Received JMX tree snapshot, class="
                + treeSnapshot.getClass().getName());
    }
}
~~~

Do not log the entire tree payload if attributes contain secrets, usernames, JDBC URLs, or sensitive data. The payload can be much larger than a single `Integer` from the attribute-polling adapter.

### 5.3. query-name, object-name, and channel are not interchangeable

~~~text
JMX query-name:   demo.integration:type=QueueStats,name=*
Spring channel:   jmxTreeSnapshots
Adapter ID:       queueTreeAdapter
MBeanServer bean: mbeanServer
~~~

`query-name` selects the set of JMX MBeans. `jmxTreeSnapshots` identifies the Spring channel. If the MBean query matches no objects, the source may return an empty structure or emit no message depending on implementation/version; test empty-tree behavior explicitly rather than assuming the system will send a fixed-format "empty event."

## 6. Converter: reducing data at the source before building the graph

By default, the tree adapter includes attributes selected by the converter. The simplest pattern to restrict it to just two attributes is:

~~~text
MBeans:
  Orders:        Depth, Healthy, ConnectionUrl, LastError, DebugInfo, ...
  Billing:       Depth, Healthy, ConnectionUrl, LastError, DebugInfo, ...
  Notifications: Depth, Healthy, ConnectionUrl, LastError, DebugInfo, ...

MBeanAttributeFilter allows: Depth, Healthy
⇒ downstream only receives a graph containing fields in this whitelist
~~~

This is **data minimization**: it lowers polling cost and reduces the risk of leaking configuration/credentials. Do not wait until sending the whole graph to Kafka before stripping sensitive fields.

### 6.1. MBeanObjectConverter

`MBeanObjectConverter` is the strategy for converting an `ObjectInstance` and server connection into a simple object:

~~~java
Object convert(
        MBeanServerConnection connection,
        ObjectInstance instance);
~~~

Spring Integration provides `DefaultMBeanObjectConverter` with a constructor accepting an `MBeanAttributeFilter`. The converter is used by the source while scanning and building the snapshot graph—it is not a Spring message converter for raw MQTT bytes or automatic JSON schemas.

### 6.2. NamedFieldsMBeanAttributeFilter

`NamedFieldsMBeanAttributeFilter` selects attributes by name:

~~~java
import org.springframework.integration.jmx.MBeanAttributeFilter;
import org.springframework.integration.jmx.NamedFieldsMBeanAttributeFilter;

MBeanAttributeFilter filter =
        new NamedFieldsMBeanAttributeFilter(
                "Depth", "Healthy");
~~~

If an MBean does not expose `Healthy`, the filter **cannot synthesize that attribute**: it only decides whether to read attributes already declared by the MBean.

**Package scope:** the snippet above uses Spring Integration **6.x**. In Spring Integration **7.x**, inbound converters, filters, and tree sources live in `org.springframework.integration.jmx.inbound`. Update imports to match your dependency version; never mix 6.x and 7.x.

### 6.3. NotNamedFieldsMBeanAttributeFilter

`NotNamedFieldsMBeanAttributeFilter` excludes attributes by name:

~~~java
import org.springframework.integration.jmx.NotNamedFieldsMBeanAttributeFilter;

var exclude =
        new NotNamedFieldsMBeanAttributeFilter(
                "JdbcPassword", "AccessToken");
~~~

A blocklist works when you want to drop known sensitive fields, but **an allowlist is safer** when MBean schemas can grow with new attributes. A newly added attribute like `ApiSecret` can slip past an old blocklist.

### 6.4. XML converter bean and filter

~~~xml
<bean id="queueTreeAttributeFilter"
      class="org.springframework.integration.jmx.NamedFieldsMBeanAttributeFilter">
    <constructor-arg>
        <array value-type="java.lang.String">
            <value>Depth</value>
            <value>Healthy</value>
        </array>
    </constructor-arg>
</bean>

<bean id="queueTreeConverter"
      class="org.springframework.integration.jmx.DefaultMBeanObjectConverter">
    <constructor-arg ref="queueTreeAttributeFilter"/>
</bean>

<int-jmx:tree-polling-channel-adapter
        id="queueTreeAdapter"
        channel="jmxTreeSnapshots"
        mbean-server="mbeanServer"
        query-name="demo.integration:type=QueueStats,name=*"
        converter="queueTreeConverter">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-jmx:tree-polling-channel-adapter>
~~~

This configuration **replaces** the converter-less adapter in section 5; do not place a second endpoint with the same `id` in the same XML. The beans above can be placed in the corresponding XML context using Spring Integration **6.x** package names. For Spring Integration 7.x, check the new package names and version-compatible XSD schema.

### 6.5. Customizing the filter per MBean

`MBeanAttributeFilter` receives both `ObjectName` and `attributeName`. You can enforce exact source + field checks:

~~~java
import javax.management.ObjectName;
import org.springframework.integration.jmx.MBeanAttributeFilter;

MBeanAttributeFilter filter =
        (ObjectName name, String attribute) ->
                "demo.integration".equals(name.getDomain())
                && "QueueStats".equals(name.getKeyProperty("type"))
                && ("Depth".equals(attribute)
                    || "Healthy".equals(attribute));
~~~

You should apply filter policies based on allowed MBean names, not just field names, when remote sources span multiple domains or trust boundaries.

## 7. Poller: cadence, message count, and source load

### 7.1. What does max-messages-per-poll=1 mean?

The tree source returns one snapshot of **multiple** MBeans per `receive()`. Thus:

~~~text
One poll task
  → one receive()
  → query Orders/Billing/Notifications MBeans
  → one graph snapshot
  → one Spring message
~~~

`max-messages-per-poll="1"` limits **how many times the source is invoked per poll task**, not how many MBeans appear in the graph. Setting it to 10 causes the same JMX tree to be queried ten times in quick succession—it does not mean "read one queue per call."

### 7.2. fixed-rate and fixed-delay

| Trigger | Semantics | What to monitor |
| --- | --- | --- |
| `fixed-delay=5000` | Waits the interval after the previous execution finishes, per scheduler semantics. | When tree queries are slow, actual cadence stretches longer. |
| `fixed-rate=5000` | Scheduled at a 5s cadence. | If tree queries are too slow, tasks may be delayed or overlap depending on scheduler/executor. |
| Cron | Captures snapshots at specific calendar hours/minutes. | Timezones and scheduled windows with no samples. |

If 500 MBeans × 20 attributes are read every 5 seconds, the system can perform roughly **10,000 attribute accesses per cycle**, not counting metadata queries and remote calls. This is a theoretical capacity example, not an exact method-call count of the converter implementation. Measure in practice with your data filter and remote latency.

### 7.3. A tree-polling cycle is not a JVM-wide transactional snapshot

A tree query can take hundreds of milliseconds or several seconds. Meanwhile, `Orders` `Depth` may already have changed by the time `Billing` is read. The resulting object graph can contain **values sampled at different instants**, not an atomic transactional snapshot of the entire `MBeanServer`. For decisions requiring cross-queue consistency, the source must provide an atomic snapshot or versioned read protocol.

### 7.4. Polling frequently repeats the same values

When nothing changes, the source produces a similar graph on the next cycle. This is expected sampling behavior, not "JMX duplicate delivery." A dashboard gauge can simply update again; triggers like sending emails need stateful change detection, hysteresis, and cooldown.

### 7.5. Rules for choosing the interval

- Prioritize limiting the number of MBeans and attributes read.
- Estimate p95/p99 scan duration for the entire graph, not just one getter.
- Set the interval larger than typical snapshot cost, or design explicit concurrency/buffering.
- Set bounds on object graph size and how sudden MBean growth is handled.
- If every short-lived event must be captured, switch to a notification/event source instead of merely shrinking the interval.


## 8. Object graph sent in the Spring Message

The tree source returns a **snapshot of a set of MBeans**, not a `Notification` or a single `Integer`. Spring Integration converts MBean data into simple objects like `Map`, `List`, arrays, and primitives so downstream flows can process it or export JSON easily. However, exact key structure, ordering, and root type should be verified on the converter version you run; do not assume a DTO with keys like `queues` or `observedAt` is generated out of the box.

### 8.1. Application-normalized JSON schema

Suppose you want to send data to a monitoring API; a transformer can produce a schema like:

~~~json
{
  "schemaVersion": 1,
  "sourceNode": "orders-service-01",
  "observedAt": "2026-11-23T03:20:00Z",
  "kind": "JMX_MBEAN_TREE_SNAPSHOT",
  "queues": [
    {
      "objectName": "demo.integration:type=QueueStats,name=Orders",
      "name": "Orders",
      "depth": 12,
      "healthy": true
    },
    {
      "objectName": "demo.integration:type=QueueStats,name=Billing",
      "name": "Billing",
      "depth": 3,
      "healthy": true
    }
  ]
}
~~~

**This is an application-designed output, not default JSON guaranteed by the native adapter.** The source only builds a graph from the query/converter. Your transformer must validate nested keys/types, and manage schema version, source identity, and timestamp.

### 8.2. A snapshot is not a whole-JMX-server transaction

MBeans can be read sequentially; `Orders` `Depth` at 03:20:00.100 and `Billing` `Depth` at 03:20:00.800 belong to two different instants. If business logic needs consistent cross-queue state, define a snapshot version/epoch or an atomic API at the source. Stamping a single `observedAt` on the graph does not turn the reads into a transaction.

### 8.3. Empty tree and failed tree must be distinguished

A `query-name` matching zero MBeans may yield an empty graph or no message depending on implementation; `IOException`/authorization/attribute getter errors can also fail a poll. **Do not interpret "no MBeans seen" as "the queues were deleted"** without verifying poll success and snapshot quality.

### 8.4. Detecting inventory diffs

~~~text
Snapshot #1: Orders, Billing
Snapshot #2: Orders, Billing, Notifications
Diff:         + Notifications
~~~

Compute business diffs only after verifying both snapshots are valid and from the same source scope; temporary disappearance caused by a remote JMX failure must not be treated as a business deletion.

## 9. Dependencies, versions, and project structure

The hands-on example uses **Java 17+, Spring Boot, and Spring Integration 6.x** to match imports available in the 6.x line:

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

Use a compatible Spring Boot BOM; never mix Spring Integration 6.x and 7.x modules. In **Spring Integration 7.x**, the inbound classes `MBeanTreePollingMessageSource`, `DefaultMBeanObjectConverter`, and `NamedFieldsMBeanAttributeFilter` are placed in `org.springframework.integration.jmx.inbound` instead of `org.springframework.integration.jmx`. Update imports from the exact API Javadocs before building.

~~~text
src/main/java/demo/jmxtree/
  JmxTreeApplication.java
  QueueStatsMBean.java
  QueueStats.java
  JmxMBeanConfiguration.java
  JmxTreeSourceConfiguration.java
  JmxTreeFlowConfiguration.java
  TreeSnapshotSink.java

src/test/java/demo/jmxtree/
  JmxTreeSourceTest.java
  JmxTreePollingTest.java
~~~

All classes belong to the `demo.jmxtree` package; each `public` class/interface is placed in a matching filename.

## 10. Example: multiple MBeans on one MBeanServer

### 10.1. Standard MBean interface

~~~java
package demo.jmxtree;

public interface QueueStatsMBean {
    int getDepth();
    boolean isHealthy();
    String getCredentialHint();
    void setDepth(int value);
}
~~~

JMX exposes attributes `Depth`, `Healthy`, and `CredentialHint`. The `CredentialHint` attribute holds **fake** data to verify that the filter excludes it from the graph—never test with real credentials. `setDepth` is for lab use; production principals should be read-only.

### 10.2. MBean implementation

~~~java
package demo.jmxtree;

import java.util.concurrent.atomic.AtomicInteger;

public class QueueStats implements QueueStatsMBean {

    private final String name;
    private final AtomicInteger depth = new AtomicInteger();

    public QueueStats(String name, int initialDepth) {
        this.name = name;
        setDepth(initialDepth);
    }

    @Override
    public int getDepth() {
        return depth.get();
    }

    @Override
    public boolean isHealthy() {
        return depth.get() < 100;
    }

    @Override
    public String getCredentialHint() {
        return "SAMPLE-NOT-A-SECRET-" + name;
    }

    @Override
    public void setDepth(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("Depth must not be negative");
        }
        depth.set(value);
    }
}
~~~

Getters do not emit notifications automatically. `isHealthy()` and `getDepth()` are two separate reads; they can observe different states if `Depth` changes between reads. If a consistent attribute pair is required, expose an immutable aggregate getter or lock/version data at the source.

### 10.3. MBeanExporter registering three queues

~~~java
package demo.jmxtree;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
class JmxMBeanConfiguration {

    static final String ORDERS =
            "demo.integration:type=QueueStats,name=Orders";
    static final String BILLING =
            "demo.integration:type=QueueStats,name=Billing";
    static final String NOTIFICATIONS =
            "demo.integration:type=QueueStats,name=Notifications";

    @Bean(name = "mbeanServer")
    MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean("ordersStats")
    QueueStats ordersStats() {
        return new QueueStats("Orders", 12);
    }

    @Bean("billingStats")
    QueueStats billingStats() {
        return new QueueStats("Billing", 3);
    }

    @Bean("notificationsStats")
    QueueStats notificationsStats() {
        return new QueueStats("Notifications", 9);
    }

    @Bean
    MBeanExporter queueStatsExporter(
            @Qualifier("mbeanServer") MBeanServer server,
            @Qualifier("ordersStats") QueueStats orders,
            @Qualifier("billingStats") QueueStats billing,
            @Qualifier("notificationsStats") QueueStats notifications) {

        var exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(
                ORDERS, orders,
                BILLING, billing,
                NOTIFICATIONS, notifications));
        return exporter;
    }
}
~~~

`@Qualifier` distinguishes the three Spring beans of the same `QueueStats` type. `MBeanExporter` registers concrete object names, not a `query-name` pattern. If an `ObjectName` is already registered by another exporter, context startup can fail; never delete MBeans not owned by the application.

## 11. Java native tree source + poller + channel

### 11.1. MBeanTreePollingMessageSource

~~~java
package demo.jmxtree;

import javax.management.MBeanServer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.jmx.DefaultMBeanObjectConverter;
import org.springframework.integration.jmx.MBeanTreePollingMessageSource;
import org.springframework.integration.jmx.NamedFieldsMBeanAttributeFilter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class JmxTreeSourceConfiguration {

    @Bean("jmx.tree.raw")
    MessageChannel treeRawChannel() {
        return new DirectChannel();
    }

    @Bean
    @InboundChannelAdapter(
            channel = "jmx.tree.raw",
            poller = @Poller(
                    fixedDelay = "5000",
                    maxMessagesPerPoll = "1"))
    MBeanTreePollingMessageSource treeSource(
            @Qualifier("mbeanServer") MBeanServer server) {

        var allowed = new NamedFieldsMBeanAttributeFilter(
                "Depth", "Healthy");
        var converter = new DefaultMBeanObjectConverter(allowed);

        var source = new MBeanTreePollingMessageSource(converter);
        source.setServer(server);
        source.setQueryName(
                "demo.integration:type=QueueStats,name=*");

        return source;
    }
}
~~~

In Spring Integration 6.x, `MBeanTreePollingMessageSource` is a native `MessageSource<Object>`; its constructor accepts an `MBeanObjectConverter`, `setServer(...)` takes an `MBeanServerConnection`, and `setQueryName(...)` sets the query pattern. `@InboundChannelAdapter` creates the polling endpoint attached to `jmx.tree.raw`. You do not need to write an `MBeanServer.queryNames` loop yourself.

For 7.x, update the imports of the three JMX inbound types to `org.springframework.integration.jmx.inbound`, verify your Java/Spring baseline, and re-test query/filter semantics.

### 11.2. IntegrationFlow receiving the whole-tree payload

~~~java
package demo.jmxtree;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

class TreeSnapshotSink {

    private final List<Object> snapshots =
            new CopyOnWriteArrayList<>();

    void add(Object graph) {
        snapshots.add(graph);
    }

    List<Object> snapshot() {
        return List.copyOf(snapshots);
    }

    void clear() {
        snapshots.clear();
    }
}
~~~

~~~java
package demo.jmxtree;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
class JmxTreeFlowConfiguration {

    @Bean
    TreeSnapshotSink treeSnapshotSink() {
        return new TreeSnapshotSink();
    }

    @Bean
    IntegrationFlow jmxTreeFlow(TreeSnapshotSink sink) {
        return IntegrationFlow.from("jmx.tree.raw")
                .handle(Object.class, (payload, headers) -> {
                    sink.add(payload);
                    return null;
                })
                .get();
    }
}
~~~

This is **one Spring message containing an object graph**—it does not automatically generate three messages just because there are three MBeans. `return null` indicates a one-way handler. The sink is strictly for lab use; it does not persist durably or bound memory over time.

### 11.3. Spring Boot entry point

~~~java
package demo.jmxtree;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JmxTreeApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                JmxTreeApplication.class, args);
    }
}
~~~

When the `@Configuration` classes in the same package are loaded, MBeans are exported, the tree source is scheduled, and `IntegrationFlow` receives snapshots. In apps with multiple Spring contexts, ensure the reader and exporter share the same `MBeanServer`; the same `ObjectName` in two different `MBeanServer`s does **not** represent a shared entity.

## 12. Manually inspecting a snapshot

First, verify the JMX source has MBeans matching the pattern:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.ObjectName;

var server = ManagementFactory.getPlatformMBeanServer();

ObjectName query = new ObjectName(
        "demo.integration:type=QueueStats,name=*");

var names = server.queryNames(query, null);

System.out.println("MBeans matched: " + names.size());
for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
~~~

This is a JMX diagnostic step; it does not trigger the Spring flow. If `names.size()==0`, fix MBean export/namespace before debugging `IntegrationFlow`.

Once the app is running, invoke in the lab:

~~~java
ordersStats.setDepth(85);
billingStats.setDepth(11);
~~~

The next poll will see a graph with the updated queue values. Do not assume the graph is returned in a fixed order, because `queryMBeans/queryNames` does not guarantee ordering; if a downstream API requires ordering, normalize and sort by `ObjectName.getCanonicalName()`.

### 12.1. Extract only the required fields

The filter on `treeSource` only allows `Depth` and `Healthy`. `CredentialHint` is a fake value that should not appear in mapped attributes. If a downstream transformer still reads or displays it, check whether the filter was applied properly and whether another endpoint is bypassing the converter.

### 12.2. A tree graph needs its own JSON contract

A DTO might look like:

~~~java
package demo.jmxtree;

import java.time.Instant;
import java.util.List;

record QueueState(
        String objectName,
        String queueName,
        int depth,
        boolean healthy) {
}

record QueueTreeSnapshot(
        String sourceNode,
        Instant observedAt,
        int schemaVersion,
        List<QueueState> queues) {
}
~~~

`QueueTreeSnapshot` is **not created automatically by the native source**. Inspect the actual graph on your target version, write a mapper with validation tests, and then export JSON. If you need one message per queue, transform into `List<QueueState>` and `split()` intentionally; do not treat an in-memory split as a durable queue.

### 12.3. Distinguish snapshots from events

Three polls returning `Orders=85` are three **observations**, not three changes. A "queue exceeded threshold" alert should be driven by state transitions/hysteresis or sustained conditions, not an email on every poll.

### 12.4. What the native adapter does not provide automatically

- No default business DTO with `observedAt`/`sourceNode`/`schemaVersion`.
- No JMS/Kafka-style ACK or replay.
- No guarantee of atomic snapshots across MBeans.
- No built-in suppression of repeated alerts while state stays unchanged.
- No automatic per-MBean downstream messages or REST endpoint.


## 13. JUnit testing MBean queries and attribute allowlists

The first test verifies the **MBeanServer API** independently of Spring scheduling; later tests verify the native source returns messages and filters data.

### 13.1. Querying an ObjectName pattern without a Spring context

~~~java
package demo.jmxtree;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

class JmxTreeQueryTest {

    @Test
    void queryFindsOnlyMatchingMBeans() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("tree-test");
        ObjectName orders = new ObjectName(
                "demo.integration:type=QueueStats,name=Orders");
        ObjectName billing = new ObjectName(
                "demo.integration:type=QueueStats,name=Billing");
        ObjectName other = new ObjectName(
                "demo.integration:type=AnotherType,name=Example");

        try {
            server.registerMBean(new QueueStats("Orders", 12), orders);
            server.registerMBean(new QueueStats("Billing", 3), billing);
            server.registerMBean(new QueueStats("Other", 7), other);

            var matched = server.queryNames(
                    new ObjectName(
                            "demo.integration:type=QueueStats,name=*"),
                    null);

            assertEquals(2, matched.size());
            assertTrue(matched.contains(orders));
            assertTrue(matched.contains(billing));
            assertFalse(matched.contains(other));

            assertEquals(12, server.getAttribute(orders, "Depth"));
            assertEquals(true,
                    server.getAttribute(billing, "Healthy"));
        } finally {
            if (server.isRegistered(orders)) {
                server.unregisterMBean(orders);
            }
            if (server.isRegistered(billing)) {
                server.unregisterMBean(billing);
            }
            if (server.isRegistered(other)) {
                server.unregisterMBean(other);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
~~~

The test uses an isolated JMX server, registers three `QueueStats` objects with one under `AnotherType`, and the `type=QueueStats` query returns only the two matching names.

In this test `QueueStats` is a Standard MBean with interface `QueueStatsMBean`; the class can be registered under `ObjectName` `type=AnotherType` because `ObjectName` is a registry name chosen by the registrant and does not require the `type` key to match the Java class/interface name. If your management environment enforces stricter naming rules, use a separate MBean class to represent a different group.

### 13.2. Testing the NamedFields filter

~~~java
package demo.jmxtree;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.integration.jmx.NamedFieldsMBeanAttributeFilter;

class JmxTreeAttributeFilterTest {

    @Test
    void allowlistRejectsUnneededFields() throws Exception {
        var filter = new NamedFieldsMBeanAttributeFilter(
                "Depth", "Healthy");

        ObjectName name = new ObjectName(
                "demo.integration:type=QueueStats,name=Orders");

        assertTrue(filter.accept(name, "Depth"));
        assertTrue(filter.accept(name, "Healthy"));
        assertFalse(filter.accept(name, "CredentialHint"));
        assertFalse(filter.accept(name, "DebugDump"));
    }
}
~~~

This test checks the `MBeanAttributeFilter` contract directly at the source; it does not prove JSON serialization or remote permissions. When upgrading to Spring Integration 7.x, update the `NamedFieldsMBeanAttributeFilter` import to `jmx.inbound`.

## 14. JUnit integrating the Spring tree source and IntegrationFlow

### 14.1. Loading Spring configuration with an in-JVM JMX server

~~~java
package demo.jmxtree;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.jmx.MBeanTreePollingMessageSource;
import org.springframework.messaging.Message;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        JmxMBeanConfiguration.class,
        JmxTreeSourceConfiguration.class,
        JmxTreeFlowConfiguration.class
})
class JmxTreeSourceTest {

    @Autowired
    @Qualifier("mbeanServer")
    MBeanServer server;

    @Autowired
    MBeanTreePollingMessageSource treeSource;

    @Test
    void treeQueryMatchesThreeQueueMBeans() throws Exception {
        ObjectName pattern = new ObjectName(
                "demo.integration:type=QueueStats,name=*");

        assertTrue(server.queryNames(pattern, null).size() >= 3);
    }

    @Test
    void nativeSourceProducesObjectGraphMessage() {
        Message<Object> result = treeSource.receive();

        assertNotNull(result);
        assertNotNull(result.getPayload());

        // Do not assume a specific graph root type or key order.
        String diagnostic = String.valueOf(result.getPayload());

        assertFalse(diagnostic.contains("SAMPLE-NOT-A-SECRET"));
    }
}
~~~

Checking that `String.valueOf(payload)` does not contain the test credential is a secondary assertion to catch obvious leakage. In production, assert the **actual graph structure** and converter behavior explicitly using fixtures/JSON mapping; stringification is not a security boundary.

This test reads directly from `MBeanTreePollingMessageSource.receive()`. It does not prove poller cadence or outbound business delivery; the test in section 14.2 covers that.

### 14.2. JUnit waiting for the Spring polling endpoint to emit a snapshot

~~~java
package demo.jmxtree;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Autowired;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        JmxMBeanConfiguration.class,
        JmxTreeSourceConfiguration.class,
        JmxTreeFlowConfiguration.class
})
class JmxTreePollingTest {

    @Autowired
    TreeSnapshotSink sink;

    @Autowired
    @Qualifier("ordersStats")
    QueueStats orders;

    @Test
    void treePollingEmitsSnapshotIntoFlow()
            throws InterruptedException {

        orders.setDepth(45);

        awaitSnapshot(Duration.ofSeconds(12));

        assertFalse(sink.snapshot().isEmpty());
        assertTrue(sink.snapshot().get(0) != null);
    }

    private void awaitSnapshot(Duration timeout)
            throws InterruptedException {

        long deadline = System.nanoTime() + timeout.toNanos();

        while (System.nanoTime() < deadline) {
            if (!sink.snapshot().isEmpty()) {
                return;
            }
            Thread.sleep(50);
        }

        throw new AssertionError(
                "No JMX tree snapshot received within test timeout");
    }
}
~~~

**Import note:** `@Autowired` in the test belongs to `org.springframework.beans.factory.annotation.Autowired`, not JUnit. This is an illustrative example; build and run real tests against your chosen Spring Boot/Spring Integration version during technical verification.

Testing a 5s poller with a 12s deadline demonstrates the asynchronous nature of scheduling. Never use `Thread.sleep(5000)` followed by a fixed assertion, since the poller may run just before or after the test starts; a bounded await is far more reliable.

### 14.3. Limitations of the tests

| Test type | What it verifies | What it does not prove |
| --- | --- | --- |
| JMX query test | `queryNames` and MBean registration/pattern. | Tree converter and Spring scheduling. |
| Filter test | Allowing/excluding attribute names. | Graph mapping, remote permissions. |
| Native source test | Source `receive()` builds payload. | Scheduler and downstream DB. |
| Polling integration test | Spring adapter + channel/flow emit snapshots. | All network failures or durable replay. |
| Remote JMX test | Real connector/auth/TLS/query latency. | Atomic snapshot across the `MBeanServer`. |

### 14.4. Test isolation and ObjectName collisions

Test contexts sharing `ManagementFactory.getPlatformMBeanServer()` may attempt to register `demo.integration:type=QueueStats,name=Orders` simultaneously. In parallel runs, this causes `InstanceAlreadyExistsException` or cross-test contamination. Use per-test-run/context ObjectNames, close contexts properly per lifecycle, or serialize tests that share the platform server. `MBeanExporter` should unregister only the MBeans it manages.

### 14.5. Do not claim a single poll captures every event

Even a test obtaining a clean snapshot after `setDepth(45)` does not prove that transitions 45 → 500 → 45 within one cycle were saved. That is a sampling limitation of the tree poller, not a JUnit bug.

## 15. Dynamic MBean registration and unregistration

One advantage of tree queries is that the set of MBeans can change from poll to poll. However, distinguish **the MBeans matched at query time**, **the attribute read window**, and **when the snapshot reaches the flow**.

### 15.1. New MBeans can appear in the next snapshot

~~~text
T0: register Orders, Billing
T1: poll → Orders, Billing
T2: register Notifications
T3: poll → Orders, Billing, Notifications (if query succeeds)
~~~

The tree source queries the registry on every poll; this differs from a notification listener registered against a fixed source. Still, if an MBean is unregistered **while** the converter is reading it, races, errors, or partial data can occur. Do not mistake the pattern for a registry-locking transaction.

### 15.2. A disappearing MBean is not necessarily a business deletion

An `ObjectName` disappearing from the graph can happen because:

- The MBean was genuinely unregistered;
- Its `ObjectName` changed in a new deployment;
- The JMX connection failed;
- Query permissions changed;
- An attribute getter or converter failed;
- The snapshot was filtered or incomplete.

The application should record snapshot quality and define how many consecutive absences signify a removed source, rather than immediately deleting a business resource.

### 15.3. Narrower queries improve stability

If the system has many domains and one group of MBeans churns frequently, use `demo.integration:type=QueueStats,name=*` instead of `*:*`. Combine field allowlists with MBean count limits, and measure query duration and source entry counts.

### 15.4. Scope data by tenant/node

Two `MBeanServer`s in two JVMs can have identical `ObjectName`s. The snapshot schema must include a trusted `sourceNode` or endpoint identity. Never merge by `ObjectName` alone and assume it is the same queue. When a remote connector reconnects to a different node, detect source identity drift.

## 16. OpenType, getter errors, and complex data types

### 16.1. A JVM MemoryMXBean example

The built-in `java.lang:type=Memory` MBean provides `HeapMemoryUsage`; the value read via `MBeanServer` is typically `CompositeData`. An overly broad tree query can pull many MXBeans and OpenTypes into the graph.

~~~java
import java.lang.management.MemoryUsage;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

Object value = server.getAttribute(
        new ObjectName("java.lang:type=Memory"),
        "HeapMemoryUsage");

if (value instanceof CompositeData data) {
    MemoryUsage usage = MemoryUsage.from(data);
    System.out.println("Used bytes=" + usage.getUsed());
}
~~~

This is a **direct JMX** example, not the return API of the default tree converter. The tree graph may normalize or flatten OpenType values differently. To extract `HeapMemoryUsage` from a tree graph, write a transformer matching the tested output shape.

### 16.2. Failure modes

| Error | Cause | Policy |
| --- | --- | --- |
| `InstanceNotFoundException` | MBean disappeared between query and attribute read. | Bounded retry / record quality; never treat as zero. |
| `AttributeNotFoundException` | MBean schema changed, attribute renamed. | Update allowlist/schema and alert. |
| `MBeanException` | MBean getter threw an exception. | Classify failing source; never retry a broken getter indefinitely. |
| `ReflectionException` | JMX invocation/accessor error. | Fix implementation or version. |
| `IOException` on remote connection | Network/RMI/TLS disruption. | Reconnect with backoff and record data gap. |
| `SecurityException` / access denied | Account lacks permission. | Fix authorization; never disable security. |
| JSON serialization failure | Graph contains an incompatible field type. | DTO mapping/allowlist, controlled quarantine. |
| Oversized graph | Overly broad query or too many MBeans. | Bound query, filter, cadence, and size. |

**Do not assume** the converter always skips all failing MBeans and returns a successful partial graph. Depending on version and error type, `receive()` may fail, log an error, or respond differently. Test fault injection in practice and distinguish failed polls from legitimate empty trees.

### 16.3. A blocking getter slows down the entire snapshot

If one MBean's `getDepth()` is fast while another's `getDebugDump()` blocks for 10 seconds, an unfiltered converter delays the whole graph. Selecting only `Depth`/`Healthy` reduces load; if an allowlisted getter still blocks, fix the source or split polling groups and bound remote connection timeouts.

## 17. Error channel, retries, and reliability

Tree polling is a **sampling source**, not a message-replaying broker. If the 12:00:05 poll fails and the 12:00:10 poll succeeds, you get the 12:00:10 snapshot; there is no built-in way to recover the exact state **that existed** at 12:00:05.

### 17.1. Classify errors by stage

~~~mermaid
flowchart TD
    POLL["Poller trigger"]
    QUERY["MBean query"]
    CONV["Converter + JMX getter"]
    CH["Spring MessageChannel"]
    NORMAL["Normalization/validation"]
    OUT["Metrics/DB/Outbox"]
    E["Error monitor / quarantine"]
    POLL --> QUERY --> CONV --> CH --> NORMAL --> OUT
    QUERY -. "IO/permissions" .-> E
    CONV -. "schema/getter" .-> E
    NORMAL -. "invalid graph" .-> E
    OUT -. "downstream failure" .-> E
~~~

- Source query error → poll fails, no valid business snapshot produced.
- Converter/attribute getter error → classify type/source, do not default to an empty graph.
- Channel dispatch error → check output subscriber and channel startup.
- Handler/transformer error → Spring Integration error path per endpoint/poller configuration.
- Downstream DB/HTTP/Kafka error → retry/buffer per that system's contract.

### 17.2. ErrorMessage does not create JMX replay

Spring Integration provides `ErrorMessage`/`errorChannel` and advice/retry for polling endpoints where appropriate, but they do not turn a JMX `MBeanServer` into a durable queue. When a specific event must be recoverable after a crash, it must be persisted at the source or in a durable inbox/outbox beforehand.

### 17.3. Backoff and retry budgets

If remote JMX is offline, tight polling with unlimited retries causes a reconnection storm. Use bounded backoff, alert when sample age exceeds SLA, and avoid queuing thousands of tasks waiting on the network. For permanent schema/permission errors, fix config/ACLs instead of fast-retrying forever.

### 17.4. Poison or oversized graphs

The converter can encounter unexpected attribute types or overly large graphs. Reject/quarantine with a reason, size, source identity, and controlled metadata; **never log the full graph** if it could contain secrets. For monitoring, degrade health status to `UNKNOWN`/`STALE` rather than substituting `Depth=0` for a failing source.


## 18. Remote JMX tree polling: connectivity, security, and recovery

`MBeanTreePollingMessageSource.setServer(MBeanServerConnection)` works with either an in-JVM server or a remote `MBeanServerConnection` obtained via `JMXConnector`. With remote JMX, the same tree query adds network latency, auth/TLS, RMI routing, and connection loss scenarios.

### 18.1. Connecting remotely in a lab environment

~~~java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

// This is a lab URL. The server does not appear automatically just by creating a URL.
JMXServiceURL url = new JMXServiceURL(
        "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi");

// secureEnvironment: Map<String, ?> provided by security configuration.
// Authentication and TLS must be enabled for remote production deployment.
JMXConnector connector =
        JMXConnectorFactory.connect(url, secureEnvironment);

MBeanServerConnection remote =
        connector.getMBeanServerConnection();

// treeSource.setServer(remote);
// When no longer in use: connector.close().
~~~

`secureEnvironment` is a placeholder for a real configuration carrying credentials and TLS policy; never use this code against unauthenticated public JMX. Manage the connector as a Spring bean with proper lifecycle/close handling. RMI may need separate registry and remote endpoint ports; in Docker/Kubernetes, verify RMI hostname, firewalls, and certificates.

### 18.2. Remote queries can be very expensive

A tree query of 500 MBeans × 20 attributes can read a huge number of properties—it is not equivalent to a tiny HTTP GET. Restrict the query domain/type, use an allowlist filter, and measure p95/p99 scan duration and serialized snapshot size. If reading the tree takes longer than the poll interval, a 5-second fixed-rate does **not** mean a new snapshot completes every five seconds.

### 18.3. Reconnect does not replay missed states

After losing a remote connection for 30 seconds, the next successful poll only yields the state **at recovery time**. MBeans that appeared and vanished during those 30 seconds may never be observed. Event history/replay requires a durable source in the emitting JVM, a JMX notification bridge, or a broker.

### 18.4. Do not merge two JVMs just because their ObjectNames match

The `ObjectName` `demo.integration:type=QueueStats,name=Orders` can exist on JVM A and JVM B. When normalizing, attach a trusted `sourceNode`/cluster ID; `ObjectName` alone is not globally unique across `MBeanServer`s.

## 19. Threading, backpressure, and resources

~~~mermaid
flowchart LR
    P["Poller"]
    Q["JMX query"]
    C["Converter/getters"]
    CH["DirectChannel"]
    D["Slow HTTP / DB handler"]
    P --> Q --> C --> CH --> D
~~~

With `DirectChannel`, the handler runs synchronously inside the polling task. If the remote query takes 8 seconds and the HTTP handler takes 10 seconds, the pipeline takes 18 seconds per sample; do not expect a poll to complete every 5 seconds merely by setting `fixed-delay="5000"`.

### 19.1. ExecutorChannel/QueueChannel do not provide durability on their own

You can decouple the source from downstream using a bounded `ExecutorChannel` or `QueueChannel`, but you must decide:

1. Thread pool size and queue capacity.
2. Full-queue policy: backpressure, reject, or drop stale.
3. Error channel for async tasks.
4. Snapshot memory size and downstream lag.
5. Draining/shutdown when the context closes.
6. That "message accepted by channel" differs from "business commit succeeded."
7. A durable inbox/outbox instead of an in-memory buffer when received data must not be lost.

### 19.2. Stale snapshots may need to be dropped

For a dashboard wanting only current gauges, replaying 500 snapshots delayed by 20 minutes produces outdated state; a latest-snapshot policy fits better. For audits or time-series, each successful snapshot needs a timestamp, retention, and likely persistence. **Choose semantics to match the goal**, rather than assuming every sample has the value of a business event.

### 19.3. Sample capacity planning

Polling 100 MBeans with 5 fields every 10 seconds reads roughly 50 fields/second on average, excluding metadata, query, and remote overhead. This is a rough estimate, not an exact method-call count. Measure in practice to tune intervals/filters and watch heap/GC.

## 20. Security: tree queries can read very broadly

A single attribute adapter targets one field; tree polling with `query-name="*:*"` can query numerous JVM MBeans and the converter may touch sensitive attributes.

### 20.1. Defense layers

- **JMX identity/authorization:** grant the remote principal only required read permissions; never grant broad invoke/write rights.
- **Query scope:** fix allowlisted domains/types/tenants; never construct `ObjectName` from untrusted input.
- **Attribute allowlist:** apply `NamedFieldsMBeanAttributeFilter` in the converter before data enters the Spring flow.
- **Payload schema:** normalize fields; never send raw unknown graphs over the Internet or to logs.
- **Transport:** TLS, authentication, hostname/certificate verification, and firewall/management network isolation.
- **Capacity:** bound MBean count, attribute count, graph size, and poll rate.
- **Audit:** log query scope, connection identity, and error types; avoid logging credentials.

### 20.2. Why a converter filter does not replace JMX ACLs

A filter stops the application from reading/forwarding unneeded fields, yet the remote credentials might still have permissions on other MBeans. If credentials leak, an attacker can bypass the app filter with their own JMX client. Enforce least privilege on the server/connector itself.

### 20.3. Testing with a fake sensitive field

`QueueStats.getCredentialHint()` intentionally returns values like `SAMPLE-NOT-A-SECRET-*`; the `Depth`/`Healthy` allowlist must exclude it. Use a synthetic sentinel instead of real secrets to test converters/serializers, and verify downstream logs/JSON contain no sentinel. Testing does not replace a security review of remote JMX permissions.

### 20.4. Do not expose an arbitrary query API

If HTTP users can submit `query-name="*:*"` directly, a monitoring endpoint becomes a tool to dump the whole JVM. Only accept allowlisted or application-defined queries, and enforce `ObjectName.quote`/escaping for key property values.

## 21. Observability and snapshot quality

| Recommended metric/field | Role |
| --- | --- |
| `jmx_tree_poll_attempts_total` | Number of poll attempts. |
| `jmx_tree_poll_success_total` | Number of successful snapshots. |
| `jmx_tree_poll_errors_total{kind}` | Breakdown by IO, MBean disappearance, schema, security. |
| `jmx_tree_poll_duration_seconds` | Time spent on JMX query + conversion. |
| `jmx_tree_last_success_epoch_seconds` | Flags stale sources. |
| `jmx_tree_matched_mbeans` | Count of MBeans matched in a successful snapshot. |
| `jmx_tree_snapshot_size_bytes` | Serialized data size. |
| `jmx_tree_normalization_errors_total` | Graphs failing the DTO contract. |
| `jmx_tree_remote_connection_up` | Status of the remote connector. |
| `jmx_tree_downstream_latency_seconds` | Handler processing duration. |
| `jmx_tree_outbox_pending_count` | Durable snapshots/events awaiting relay. |
| `jmx_tree_dropped_total{reason}` | Snapshots dropped by policy. |

These are **suggested metric names**, not names emitted automatically by Spring Integration by default. Do not attach individual `ObjectName`s or snapshot timestamps as high-cardinality metric labels; use properly access-controlled structured logs/traces.

### 21.1. Normal and failure traces

~~~text
03:00:00 TREE_POLL_TRIGGERED
03:00:00 JMX_QUERY_OK matched=3
03:00:00 CONVERT_OK allowedFields=Depth,Healthy
03:00:00 SPRING_CHANNEL_DISPATCHED
03:00:00 DASHBOARD_SNAPSHOT_UPDATED
~~~

~~~text
03:00:05 TREE_POLL_TRIGGERED
03:00:10 JMX_QUERY_FAILED kind=IOException
03:00:10 SOURCE_STALE
03:00:10 LAST_KNOWN_VALUES_RETAINED, quality=STALE
~~~

Never replace a failed poll with an empty graph or `Depth=0` and report that the queues vanished. Source quality must be tracked separately.

### 21.2. Readiness is more than the endpoint being RUNNING

A polling endpoint can be RUNNING even when its connection is broken. Track `lastSuccessfulSnapshotAt`, query scope, matched-count trends, converter errors, and downstream backlog. Alert after exceeding an SLA threshold of consecutive cycles without a valid snapshot.

## 22. Common troubleshooting

| Symptom | What to check? | Resolution |
| --- | --- | --- |
| Tree snapshot does not reach channel | Is poller/endpoint running? Is there a consumer? | Check XML/Java configuration and error path. |
| Zero MBeans matched | Wrong `query-name` or `MBeanServer`. | Call `queryNames(pattern,null)` on the exact server. |
| Received one message instead of three | Tree source emits one graph containing multiple MBeans. | Expected behavior; normalize and split if needed. |
| Converter reads too many fields | Missing allowlist. | Use `NamedFieldsMBeanAttributeFilter`. |
| Missing `Depth` field | Wrong attribute case, or filter checks `getDepth`. | Inspect `MBeanInfo` and use `Depth`. |
| JSON differs from example | Graph root/keys differ from assumed DTO. | Write an explicit mapper with versioned fixtures. |
| Empty graph right after startup | MBeans not registered yet. | Check `MBeanExporter` lifecycle. |
| Dynamic MBean flickers in/out | Register/unregister race during query. | Track snapshot quality, retries, and sampling timing. |
| Converter timeout | Heavy getter or remote latency. | Narrow query, filter attributes, split source groups. |
| `CompositeData` cast error | OpenType differs from Java primitives. | Convert using the proper schema/API. |
| Fake sensitive field appears in graph | Misconfigured filter or another endpoint bypassing it. | Test allowlist, output redaction, and ACLs. |
| Oversized graph grows heap | Wildcard too broad, keeping many snapshots in RAM. | Bound query, buffers, and retention. |
| Remote JMX connection lost | TLS/RMI hostname/ports/firewall. | Inspect connector and reconnect/backoff. |
| CI reports `ObjectName` already registered | Contexts share the platform server. | Unique test ObjectNames, cleanup, or serial tests. |
| Java import errors | Using 6.x package with 7.x dependency. | Switch `jmx` to `jmx.inbound` accordingly. |
| Repeated alerts sent | Same tree state across multiple polls. | Stateful transition/hysteresis/cooldown. |
| Missed short spike | Tree poll is not an event listener. | Use JMX notifications or a durable event source. |

### 22.1. Debug JMX before Spring Integration

~~~java
ObjectName pattern = new ObjectName(
        "demo.integration:type=QueueStats,name=*");

var names = mbeanServer.queryNames(pattern, null);
System.out.println("Matched MBeans = " + names.size());
~~~

If matched-count is 0, fix MBean registration/namespace before debugging the converter. If the query succeeds but the Spring channel receives nothing, inspect the source, `@Poller`, error logs, output channel, and flow. If the channel receives messages but DB/Kafka lacks data, inspect downstream transforms, serializers, and transactions.

## 23. Anti-patterns and replacements

| Anti-pattern | Why it is wrong | Fix |
| --- | --- | --- |
| `query-name="*:*"` then filtering secrets downstream. | Reads too broadly and secrets already entered memory. | Narrow query + converter allowlist / JMX ACLs. |
| Assuming `max-messages-per-poll=5` means five MBeans. | A single `receive` can scan the whole tree. | Typically `1` to get one graph snapshot. |
| Assuming tree payload is `QueueTreeSnapshot` by default. | Native source returns a converter graph. | Explicit DTO mapper with contract/fixtures. |
| Treating an empty graph as deleted queues. | Poll/query can fail. | Check quality/error metadata before inventory decisions. |
| Sending an alert on every poll above threshold. | Sampling produces multiple snapshots in the same state. | Hysteresis/transition filter. |
| Treating the graph as an atomic snapshot. | MBeans/attributes are read at different instants. | Versioned/atomic state API at source if needed. |
| Increasing poll speed to guarantee catching all changes. | Brief transitions can still be missed. | Notifications or event history. |
| Sending raw graphs to Kafka/HTTP. | Risks leaking fields and unstable schemas/serialization. | Versioned DTO, allowlist/redaction. |
| Not closing remote `JMXConnector`. | Leaks sockets and threads. | Lifecycle-managed close. |
| Treating `ExecutorChannel` as a durable queue. | In-memory messages are lost on crash. | Durable inbox/outbox. |
| Using `ObjectName` as a global multi-JVM key. | Names collide across nodes. | Source node ID + `ObjectName`. |
| Retrying forever on permission denied. | Does not fix config errors and creates load. | Alert/fix auth, bounded retries. |

## 24. Exercise: monitoring multiple queues with a JMX tree

**Scenario:** Five JVMs each expose multiple `QueueStats` MBeans. A Spring Integration service collects snapshots every 10 seconds to update a dashboard, alert on overload, and send aggregated snapshots to HTTP/Kafka.

### 24.1. Tasks to complete

1. Create `QueueStatsMBean` with `Depth`, `Healthy`, and a **fake** sensitive field `CredentialHint`.
2. Export three MBeans `Orders`, `Billing`, and `Notifications` under the same domain/type.
3. Verify the pattern using `queryNames(new ObjectName("demo.integration:type=QueueStats,name=*"),null)`.
4. Configure a native XML `tree-polling-channel-adapter` with `query-name`, a 10-second poller, and `max-messages-per-poll=1`.
5. Configure a native Java `MBeanTreePollingMessageSource` with converter and allowlist.
6. Route the graph through a `MessageChannel` to an `IntegrationFlow`.
7. Inspect a real payload on your target version; write a mapper to a DTO with `sourceNode`/`observedAt`/`schemaVersion`/`queues`.
8. Assert the DTO does not contain `CredentialHint` and only includes `Depth`/`Healthy`.
9. Test that a newly registered MBean name appears in the next successful snapshot, and likewise when unregistered.
10. Test attribute schema mismatch, getter error, and remote disconnect; use STALE/UNKNOWN rather than `Depth=0`.
11. Use an in-JVM `MBeanServer` and JUnit to test `queryNames`, the filter, `receive()`, and the scheduled flow.
12. Verify isolation across multiple test contexts on the platform `MBeanServer`.
13. Simulate remote latency > poll interval; measure backlog and latency.
14. Measure MBean counts, allowed attribute counts, and serialized graph size.
15. Implement stateful severity/hysteresis to avoid sending alerts on every snapshot.
16. Convert output to a JSON DTO and send to HTTP/Kafka via an outbox if durability is required.
17. Test relay timeouts/crashes and consumer idempotency.
18. Secure remote JMX with TLS, authentication, read-only roles, and firewalls.
19. Build a dashboard for poll successes/failures, last-success age, and snapshot quality.
20. Explain why tree polling does not guarantee capturing every brief transition or providing atomic cross-MBean state.

**Acceptance criteria:** native tree polling source, converter allowlist, one graph message per source receive, JUnit tests for JMX + Spring flow, schema normalization, error/staleness policy, security, and clearly documented delivery limitations.

## 25. Self-check questions

1. Is JMX tree polling inbound or outbound?
2. How does tree polling differ from attribute polling?
3. Does `query-name` select MBeans or attributes?
4. What is the role of `MBeanAttributeFilter`?
5. How does `NamedFieldsMBeanAttributeFilter` differ from `NotNamedFieldsMBeanAttributeFilter`?
6. Why does an allowlist carry less risk than a blocklist?
7. Through which API does `MBeanTreePollingMessageSource` receive a converter?
8. What JMX type does `setServer(...)` accept?
9. How does `setQueryName(...)` differ from `setObjectName(...)` on the attribute source?
10. How many MBeans can one poll contain, and how many Spring messages does it emit?
11. Does `max-messages-per-poll=1` limit the number of MBeans?
12. Why is a snapshot not atomic across multiple MBeans?
13. Does the converter using `Map`/`List`/arrays mean the JSON schema is fixed automatically?
14. Why should the application define `observedAt` and `sourceNode`?
15. If an MBean disappears from the tree, is it guaranteed to have been deleted?
16. If a remote query fails, should you emit an empty graph as the inventory?
17. Is a spike shorter than the poll interval guaranteed to be observed?
18. Why is an attribute filter at the source better than stripping fields after JSON serialization?
19. How does Spring Integration 7.x change the JMX inbound package?
20. What does a `queryNames` unit test prove?
21. How does a native source `receive()` test differ from a scheduled flow test?
22. Why does the platform `MBeanServer` cause collisions during parallel tests?
23. How does `DirectChannel` + a slow HTTP handler affect the poller?
24. Does `ExecutorChannel` persist messages across restarts automatically?
25. Which layers must be secured for remote JMX?
26. Is `ObjectName` sufficient as a business identity across two JVMs?
27. Does a RUNNING poller mean the data is definitely fresh?
28. Why can downstream Kafka not reconstruct a spike that the source never polled?
29. When should you choose notification listening over tree polling?
30. Which metrics help distinguish a successful empty snapshot from a failed poll?

**Hint:** Remember the four boundaries: **JMX query → converter/filter → Spring poller/MessageChannel → business DTO/downstream**. A snapshot is a **state observation**, not a complete list of events since the previous poll.

## 26. Conclusion and references

Spring Integration's **JMX tree-polling adapter** queries a group of MBeans by `query-name`, uses a converter to construct an object graph, and emits a Spring `Message` on a poller schedule:

- Native XML `int-jmx:tree-polling-channel-adapter` or native Java `MBeanTreePollingMessageSource`.
- `DefaultMBeanObjectConverter` and `NamedFieldsMBeanAttributeFilter` restrict attributes at the source.
- `max-messages-per-poll` controls the number of `receive()` calls per poll task, not the number of MBeans in the tree.
- The object graph is well-suited for normalization and JSON serialization, but requires an application-defined schema, source identity, timestamp, and validation.
- Polling can miss transitions; graphs are not atomic across MBeans, and JMX provides no durable ACK/replay by default.
- Query scoping, filters, remote TLS/auth, resource bounds, error handling, and stale-source metrics prevent misleading monitoring.
- When downstream durability is required, use an inbox/outbox and idempotent consumers; when zero missed events is required, choose JMX notifications or a history-backed event source.

In **SPRING_INTEGRATION_ADAPTERS**, the flow **JMX tree → MessageChannel → IntegrationFlow → DB/HTTP/JMS/AMQP/Kafka/file/SFTP** demonstrates applying a unified message contract and integration pipeline to JVM management data. Distinguishing **snapshot sampling**, **delivery**, and **business commit** is essential for truthful status reporting.

### 26.1. Official API references

- [Spring Integration JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html): native tree adapter, `query-name`, converter, and filters.
- [Spring Integration 6.x MBeanTreePollingMessageSource Javadoc](https://www.springframework.org/spring-integration/docs/6.4.0-M2/api/org/springframework/integration/jmx/MBeanTreePollingMessageSource.html): constructor and source methods.
- [Spring Integration 6.x MBeanObjectConverter](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/jmx/MBeanObjectConverter.html): converter interface.
- [Spring Integration 7.x JMX inbound package](https://docs.spring.io/spring-integration/api/org/springframework/integration/jmx/inbound/package-summary.html): package migration.
- [Java 17 JMX APIs](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/package-summary.html): `MBeanServerConnection`/`ObjectName`/`QueryExp`/`MBeanInfo`.

**STEP 4 scope:** This article focuses on creating detailed Knowledge content and learning examples. When applying it to a real project, verify dependency versions and run appropriate tests. Technical Content QA/refactoring will be performed in **STEP 6**, not as part of this STEP 4 authoring pass.




