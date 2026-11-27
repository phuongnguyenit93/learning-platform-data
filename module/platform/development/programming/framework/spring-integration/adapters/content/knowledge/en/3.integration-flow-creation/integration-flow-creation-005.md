# Configuring Adapters with XML Namespaces

## 1. Objectives and Role of XML Namespaces in Spring Integration

In the **Integration Flow Creation** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, a flow can be configured using the Java DSL, annotations, or XML. **XML namespaces** allow declaring integration components using dedicated XML tags: channels, inbound/outbound adapters, gateways, pollers, transformers, and service activators. Spring parses that configuration when creating the application context and registers the corresponding beans and endpoints.

The module scope covers connecting external systems via **inbound/outbound adapters, gateways, pollers, and `MessageChannel`**, practicing with **files, SFTP, HTTP, JMS, AMQP, Kafka, and databases**, while understanding **message contracts, errors, and connection lifecycles**. XML namespaces are useful when an application already uses XML configuration or when you want the integration topology expressed centrally in a single configuration file.

After this lesson, learners will be able to:

- Read and declare `xmlns:int` alongside adapter namespaces such as `int-file`, `int-sftp`, `int-http`, or `int-jms`.
- Write a complete inbound file flow in XML: **file source → poller → channel → service activator**.
- Understand bean IDs, channel names, schema locations, dependencies, and how XML is imported into Spring Boot.
- Configure an outbound adapter and distinguish a one-way adapter from a request–reply gateway.
- Diagnose and fix common issues: channels without consumers, missing pollers, mismatched bean names, duplicates, timeouts, and connection resources.
- Test both XML wiring and real behavior of sources and target systems.

**Remember:** XML is only a **configuration representation**. At runtime, execution still relies on Spring Integration objects such as `Message<?>`, `MessageChannel`, `MessageSource`, `MessageHandler`, and endpoints.

## 2. Structural Diagram of an XML Integration Flow

~~~mermaid
flowchart LR
    A["External source<br/>file / SFTP / DB"]
    B["Inbound adapter"]
    P["Poller"]
    C["MessageChannel"]
    T["Transformer / Filter / Router"]
    D["MessageChannel"]
    E["Service activator<br/>or outbound adapter"]
    F["Target system"]
    P -. "triggers receive()" .-> B
    A --> B --> C --> T --> D --> E --> F
~~~

| XML Element | Role | Example |
| --- | --- | --- |
| `<int:channel>` | Creates a channel connecting producers and consumers. | `<int:channel id="files.input"/>`. |
| `<int-file:inbound-channel-adapter>` | Reads files from a directory and emits `Message<File>`. | Polls `./inbox`. |
| `<int:poller>` | Sets the schedule and maximum messages fetched per poll. | `fixed-delay="5000"`. |
| `<int:transformer>` | Transforms a message's payload. | `File` to path or DTO. |
| `<int:filter>` | Allows only qualifying messages to continue. | Drops messages failing criteria. |
| `<int:service-activator>` | Invokes a Java method upon receiving a message. | Calls a CSV reading service. |
| `<int-file:outbound-channel-adapter>` | Writes a message to a file at the destination. | Writes files to an export directory. |
| Namespace gateway | Connects a request–reply boundary to a flow. | Messaging gateway or HTTP gateway. |

An **inbound** adapter brings external data into a channel. An **outbound** adapter takes messages from a channel and sends data outward. A **gateway** typically defines a reply contract; a **poller** applies to endpoints that actively pull data—not every endpoint needs a poller.

For instance, an HTTP inbound gateway is typically triggered by incoming HTTP requests, whereas a file inbound adapter must scan a directory on a schedule.

## 3. Declaring Namespaces, Schemas, and Dependencies

### 3.1. What Problem Do XML Namespaces Solve?

Instead of manually declaring individual factory beans, listeners, and polling endpoints, you use domain-specific tags:

~~~xml
<int:channel id="files.input"/>

<int-file:inbound-channel-adapter
        id="csvInbound"
        channel="files.input"
        directory="${adapter.inbox}"
        filename-pattern="*.csv">
    <int:poller fixed-delay="5000" max-messages-per-poll="5"/>
</int-file:inbound-channel-adapter>
~~~

Spring Integration processes `<int-file:inbound-channel-adapter>` to register **the message source and polling endpoint**. The `int` namespace creates the channel and poller. `files.input` is the channel bean name wiring components together, while `csvInbound` identifies the adapter endpoint for management and observability.

### 3.2. Declaring All Required Namespaces

A skeleton XML file containing a file inbound adapter looks like:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:int-file="http://www.springframework.org/schema/integration/file"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           http://www.springframework.org/schema/context/spring-context.xsd
           http://www.springframework.org/schema/integration
           http://www.springframework.org/schema/integration/spring-integration.xsd
           http://www.springframework.org/schema/integration/file
           http://www.springframework.org/schema/integration/file/spring-integration-file.xsd">

    <!-- Declare channels, adapters, pollers, and handlers here. -->

</beans>
~~~

Entries in `xsi:schemaLocation` come in **pairs of namespace URI and XSD location**. Prefixes like `int` or `int-file` are aliases chosen by the author; the URI defines the actual namespace. The XML parser uses the namespace URI, schema, and Spring namespace handlers to interpret tags.

Do not declare `xmlns:int-file` and use `<int-file:...>` unless `spring-integration-file` is on the classpath: the corresponding parser and implementation are provided by that adapter module. Similarly, adding a namespace to XML does not by itself establish a connection to JMS, SFTP, or Kafka.

### 3.3. Minimal Maven Dependencies

With Spring Boot managing dependency versions:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-file</artifactId>
</dependency>
~~~

The starter supplies integration core and Boot auto-configuration. `spring-integration-file` provides the file adapter and its XML namespace. When using SFTP, HTTP, JMS, AMQP, Kafka, or JDBC, add the corresponding Spring Integration dependency, plus any required client drivers, connection factories, or protocol libraries.

**Versioning note:** prefer letting the Spring Boot BOM manage Spring Integration versions across the project. Do not arbitrarily mix Spring Integration modules from different release lines, as namespace parsers, APIs, and adapter behaviors may be incompatible.

## 4. Complete Example: Reading CSV Files with an XML Inbound Adapter

Problem: an application monitors `./inbox`, scans for `.csv` files every 5 seconds, and passes each `File` to a Java service. This is a practice example of **wiring a file source**, not a production-hardened CSV ingestion pipeline.

### 4.1. Sample File Structure

~~~text
src/main/java/demo/xmladapter/
    XmlAdapterApplication.java
    CsvFileProcessor.java

src/main/resources/
    adapter.properties
    integration/file-flow.xml
~~~

The `./inbox` directory is relative to the **working directory at runtime**, not automatically `src/main/resources`. Create this directory before startup or ensure a step creates it explicitly.

### 4.2. Configuring integration/file-flow.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:int-file="http://www.springframework.org/schema/integration/file"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           http://www.springframework.org/schema/context/spring-context.xsd
           http://www.springframework.org/schema/integration
           http://www.springframework.org/schema/integration/spring-integration.xsd
           http://www.springframework.org/schema/integration/file
           http://www.springframework.org/schema/integration/file/spring-integration-file.xsd">

    <context:property-placeholder
            location="classpath:adapter.properties"/>

    <!-- 1. Channel receiving File messages from the adapter. -->
    <int:channel id="files.input"/>

    <!-- 2. Java bean processing messages from the channel. -->
    <bean id="csvFileProcessor"
          class="demo.xmladapter.CsvFileProcessor"/>

    <!-- 3. Inbound adapter actively scanning for CSV files. -->
    <int-file:inbound-channel-adapter
            id="csvInbound"
            channel="files.input"
            directory="${adapter.inbox}"
            filename-pattern="*.csv">
        <int:poller
                fixed-delay="5000"
                max-messages-per-poll="5"/>
    </int-file:inbound-channel-adapter>

    <!-- 4. Consumer executing the final operation. -->
    <int:service-activator
            id="processCsv"
            input-channel="files.input"
            ref="csvFileProcessor"
            method="process"/>

</beans>
~~~

`src/main/resources/adapter.properties`:

~~~properties
adapter.inbox=./inbox
~~~

The key connection point is the channel name **`files.input`**: the adapter sends messages to this channel, and the service activator subscribes to that exact channel.

### 4.3. File Processor Class

~~~java
package demo.xmladapter;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class CsvFileProcessor {

    private final Set<Path> handledFiles =
            ConcurrentHashMap.newKeySet();

    public void process(File file) throws IOException {
        Path path = file.toPath().toRealPath();
        String contents = Files.readString(path, StandardCharsets.UTF_8);

        // Demo only reads content and records the path.
        System.out.printf("Received CSV: %s (%d chars)%n",
                path, contents.length());
        handledFiles.add(path);
    }

    public boolean wasHandled(Path file) throws IOException {
        return handledFiles.contains(file.toRealPath());
    }
}
~~~

Because `CsvFileProcessor` is declared with `<bean>` in XML, do not also add `@Component`, which would create a **second bean**. `process(File)` is invoked whenever a message with a `File` payload arrives on `files.input`.

In this example, `handledFiles` only supports testing and observation **within the running process**. It is not a persistent checkpoint store. If the handler fails after the source has marked a file as read, the endpoint will not automatically recover that file simply because a Java `Set` exists.

### 4.4. Importing XML into a Spring Boot Application

~~~java
package demo.xmladapter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ImportResource;

@SpringBootApplication
@ImportResource("classpath:integration/file-flow.xml")
public class XmlAdapterApplication {

    public static void main(String[] args) {
        SpringApplication.run(XmlAdapterApplication.class, args);
    }
}
~~~

`@ImportResource` tells Spring to load bean definitions from XML. The channel, inbound adapter, service activator, and processor beans reside in the **same application context** as Spring Boot's Java beans.

Traditional Spring apps can use a standalone XML context; in Boot, `@ImportResource` blends XML with Java configuration and dependency injection. Do not manually define the same channel or adapter again with `@Bean`.

### 4.5. Tracing One Poll Cycle

Suppose the directory holds three files:

~~~text
./inbox/
    order-01.csv
    order-02.csv
    note.txt
~~~

With `filename-pattern="*.csv"`, the file source selects matching CSV files. Each poll cycle can take up to five messages per `max-messages-per-poll="5"`; since only two CSV files exist, fewer messages are emitted. `note.txt` is excluded by the source filter.

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant A as csvInbound
    participant C as files.input
    participant S as CsvFileProcessor
    P->>A: Triggers on fixed-delay
    A->>A: Finds *.csv files
    A->>C: Message<File>(order-01.csv)
    C->>S: process(File)
    A->>C: Message<File>(order-02.csv)
    C->>S: process(File)
    P-->>P: Ends cycle, waits for next schedule
~~~

Whether a file is emitted again on a later poll or after a restart depends on **filters, stored state, and source behavior**. Filename filtering does not replace a deduplication strategy. If a file must be processed only once across restarts, use an archive/checkpoint policy or a persistent-state filter.

## 5. XML Adapter Attributes to Understand

| Attribute / Element | Meaning | Questions to Answer When Configuring |
| --- | --- | --- |
| `id` | Endpoint/bean name for management and monitoring. | Does it collide with another bean name? |
| `channel` | Channel to which the inbound adapter sends messages. | Is a consumer subscribed to it? |
| `directory` | Source/target directory for file adapters. | What are the actual path and file permissions? |
| `filename-pattern` | Pattern selecting source filenames. | Could it miss files or pick up partially written files? |
| `<int:poller>` | Schedule for polling the source. | Is polling fast or slow; does processing block the thread? |
| `max-messages-per-poll` | Maximum messages fetched in **one** poll cycle. | How should source and consumer load be bounded? |
| `input-channel` | Channel from which a service activator or transformer reads. | Does the name match the previous step's output? |
| `ref` / `method` | Target Java bean and method to invoke. | Is that bean created by Spring; does the method accept the payload type? |

In XML, a tiny typo like `files.inputs` instead of `files.input` can route messages to the wrong channel or leave them without a consumer. Name channels consistently across flow stages and keep payload mappings clear between endpoints.

### 5.1. Poller Limits Are Not Business Batching

For example:

~~~xml
<int:poller fixed-delay="2000" max-messages-per-poll="10"/>
~~~

This means one cycle can fetch at most **10 messages** from the source, not that the framework bundles them into a single `Message<List<File>>`. If the source returns one message containing a list of 100 records, `10` still counts **messages**, not individual list elements.

`fixed-delay` sets a delay between the end of one run and the start of the next; `fixed-rate` targets a fixed interval from start times; `cron` follows a calendar expression. Pick one trigger type and verify effective throughput when handlers are slow.

### 5.2. Polling and Error Paths

When a service activator or outbound handler throws an exception while the poller dispatches a message over a synchronous channel, the error surfaces inside the poll execution; error handling depends on the scheduler, endpoint, and error channel/advice setup. If processing already crossed into a queue, executor, or broker, the exception may occur on another thread without returning to the poller.

Therefore distinguish:

1. **Source read failure:** failed to fetch the file or record; source-level retry may be needed.
2. **Message received but processing failed:** inspect source state, retries, and ability to replay that exact message.
3. **Written to external system but response lost:** risk of duplicates if retries lack idempotency.

A poller firing again on schedule **does not guarantee** failed messages are automatically retried.

## 6. Configuring Outbound Adapters with XML Namespaces

XML namespaces also declare **outbound flows to external systems**. For a file outbound adapter, suppose a channel receives file messages to export to another directory:

~~~xml
<!-- Add these declarations inside <beans> with int and int-file namespaces. -->
<int:channel id="files.toExport"/>

<int-file:outbound-channel-adapter
        id="csvOutbound"
        channel="files.toExport"
        directory="${adapter.outbox}"/>
~~~

Additional property:

~~~properties
adapter.outbox=./outbox
~~~

If the adapter receives a compatible `Message<File>`, the file outbound endpoint writes/copies data into the target directory according to the file-writing handler rules. Filenames, behavior when the destination file already exists, directory creation, temp-write/rename behavior, and permissions must be checked against your adapter configuration and version.

Java example sending a message **to the outbound channel**, assuming the channel bean is injected:

~~~java
Message<File> message = MessageBuilder
        .withPayload(new File("./inbox/order-01.csv"))
        .build();

boolean accepted = filesToExportChannel.send(message);
~~~

`accepted` reflects the send operation on Spring's `MessageChannel`. Never treat it as proof that the file is safely stored on the target system or processed by the recipient. With a `DirectChannel`, a synchronous handler can throw right inside `send`; with async/queue channels, confirmation timing differs.

**Example note:** the outbound snippet is standalone. If combined with section 4's example, do not casually insert an `<int:bridge>` from `files.input` to `files.toExport` while a service activator already subscribes to `files.input`: point-to-point channels do not duplicate messages to every consumer by default. If you need both CSV processing and file export, define the flow, transfer points, and fan-out semantics explicitly.

## 7. Transformers, Filters, and Service Activators in XML

Beyond adapters, the core namespace lets you wire processing stages:

~~~xml
<int:channel id="files.raw"/>
<int:channel id="files.paths"/>

<int:transformer
        input-channel="files.raw"
        output-channel="files.paths"
        expression="payload.absolutePath"/>

<bean id="pathHandler" class="demo.xmladapter.PathHandler"/>

<int:service-activator
        input-channel="files.paths"
        ref="pathHandler"
        method="handle"/>
~~~

The snippet above is a **separate illustrative flow**. `<int:transformer>` uses Spring Expression Language (SpEL) to convert a `File` payload into an absolute path `String`. `PathHandler.handle(String path)` is an application method you must supply; this class is not created in section 4's runnable example.

To filter messages after an adapter emits them, use the core filter:

~~~xml
<int:filter input-channel="events.raw"
            output-channel="events.valid"
            expression="payload != null"/>
~~~

This example only illustrates expression syntax; in standard Spring Integration sources, a `Message<?>` payload must already be non-null, so that condition adds virtually no business validation. In real implementations, replace it with real rules (valid transaction code, update date, allowed origin, etc.).

**Key distinction:** a file filter at the source decides **which files are emitted as messages**; a filter inside the flow decides **which messages continue**. When an in-flow filter drops a message while an upstream request–reply gateway awaits a result, specify an error or rejection response to avoid unexplained timeouts.

## 8. Common Adapter Namespaces in This Module

Each protocol adapter has its own namespace and dependency. Prefixes may vary, but the namespace URI must be exact and supported by its module on the classpath.

| Group | Common Prefix | Endpoints / Purpose | Implementation Notes |
| --- | --- | --- | --- |
| File | `int-file` | File inbound/outbound adapters. | Directories, filters, in-progress files, temp write and rename. |
| SFTP | `int-sftp` | Sync/read files from server, upload files. | Session factory, remote paths, reconnects, local cache. |
| HTTP | `int-http` | HTTP inbound/outbound gateways or adapters. | URL/path, method, status codes, timeouts, body/header mapping. |
| JMS | `int-jms` | Message-driven inbound, outbound adapters/gateways. | ConnectionFactory, destinations, acks, transactions. |
| AMQP | `int-amqp` | Listeners and outbound adapters/gateways. | Exchanges, routing keys, queues, publisher confirms. |
| Kafka | `int-kafka` | Kafka inbound/outbound endpoints per module. | Topics/partitions, offset commits, serialization, retries. |
| JDBC / database | `int-jdbc` | Query polling and database writes. | DataSource, queries, checkpoints, transactions, locking. |

For example, declaring SFTP XML typically requires:

~~~xml
xmlns:int-sftp="http://www.springframework.org/schema/integration/sftp"
~~~

Plus the SFTP namespace/XSD pair in `xsi:schemaLocation`, the `spring-integration-sftp` dependency, and a session factory bean. Missing any of these leaves the configuration incomplete for a real connection. Never copy an SFTP tag and expect Spring to infer host, credentials, remote directory, and host-key verification policies.

**Note:** XML attribute support varies by Spring Integration version. Check the XSD and documentation for **the exact dependency version in use** before copying attributes from legacy examples.

### 8.1. When Does Inbound Require a Poller?

- **File, SFTP, or JDBC polling:** typically uses a poller because the source is actively checked on a schedule.
- **HTTP inbound gateway:** requests arrive from the HTTP server; no generic poller is needed to receive requests.
- **JMS/AMQP/Kafka message-driven inbound:** listener containers and brokers drive delivery; typically does not use `<int:poller>` like file inbound adapters.

Do not equate having a message queue with needing a polling adapter. Each protocol has its own delivery, acknowledgement, and transaction semantics.

## 9. How Does XML Gateway Configuration Differ from Outbound Adapters?

An XML messaging gateway creates a proxy for a Java interface. For example, assuming `demo.xmladapter.OrderGateway` exists:

~~~xml
<int:gateway
        id="orderGateway"
        service-interface="demo.xmladapter.OrderGateway"
        default-request-channel="orders.requests"/>
~~~

This tag expresses **Java method → request message channel**. If the method has a return value, the flow must produce an appropriate reply.

By contrast, an HTTP outbound gateway expresses **in-flow message → HTTP request → reply**, while a file outbound adapter primarily expresses **in-flow message → one-way file write**. Never choose a gateway merely because the topic mentions "adapter": base the decision on the data contract and whether a reply is required.

| Scenario | Component | Result Path |
| --- | --- | --- |
| Java caller invokes a flow like a service. | `<int:gateway>` or `@MessagingGateway`. | Reply returned to the Java method if present. |
| Flow receives an HTTP request from an external client. | HTTP inbound gateway. | HTTP response returned to the client. |
| Flow calls a partner API and needs the response. | HTTP outbound gateway. | Response brought back into the flow. |
| Flow writes a target file with no business reply. | File outbound adapter. | Typically one-way termination; check write errors. |
| Flow scans a directory every few seconds. | File inbound adapter + poller. | Emits messages when files appear; no caller awaits a reply. |

XML and Java DSL can coexist in the same application context: XML declares channels and adapters while Java DSL registers flow consumers for those channels. Just be careful **not to accidentally redefine beans with the same name, register competing consumers on a `DirectChannel`, or duplicate endpoints polling the same source**.

## 10. XML vs. Java DSL and Annotations

The same integration topology can be expressed in multiple ways:

| Criterion | XML Namespace | Java DSL / Annotations |
| --- | --- | --- |
| Where config lives | XML files, property placeholders, bean references. | Java classes, `@Bean` methods, DSL, and annotations. |
| Topology visibility | Entire bean/channel/endpoint graph readable in one file. | Navigable via IDE, Java types, and refactoring tools. |
| Channel name checks | Usually string IDs/refs checked at context startup. | Can also use strings, plus typed bean references. |
| Business logic reuse | Java beans referenced by `ref`/`method`. | Beans injected directly into DSL/handler methods. |
| Adapter configuration | Module namespaces and schemas. | Module adapter factories, DSL builders, and handler APIs. |
| Migration | Can migrate flow by flow without duplicating beans. | Can reuse the same services and declared channels. |

Section 4's XML example expresses the chain:

~~~text
int-file:inbound-channel-adapter
    → int:channel
    → int:service-activator
    → CsvFileProcessor.process(File)
~~~

In the Java DSL, the equivalent defines an `IntegrationFlow` starting from a file inbound source with a poller, followed by `.handle(...)` calling the processor. The `File` contract does not need to change if both styles emit compatible messages.

Long-lived applications can continue using XML namespaces. When migrating incrementally to the DSL, keep interaction points stable: **channel names, DTOs/payloads, headers, retry semantics, transactions, and endpoint lifecycles**.

## 11. Controlling Errors and Connection Lifecycles

### 11.1. Stages to Observe

A typical outbound flow passes through:

1. **Read succeeded:** inbound adapter found/fetched the file or record.
2. **Message handed off:** source sent the message over `MessageChannel`.
3. **Internal processing succeeded:** transformers/handlers completed.
4. **Delivered to destination:** outbound adapter/client reports sent or protocol ack received.
5. **Business completion at target:** target system confirmed processing per contract.

Never infer step 5 from step 2 or 3. If a file was marked "read" before an outbound HTTP call failed, define a clear **retry/replay** strategy. If HTTP succeeded but the response was lost, retrying without idempotency can create duplicate records.

### 11.2. Where Do Errors Appear?

| Error Category | Example | Handling Design |
| --- | --- | --- |
| XML startup | Missing namespace parser, invalid schema, missing bean ID. | Check startup logs, dependencies, XSDs, and bean refs. |
| Connection / source | SFTP session timeout, DB unavailable, file permissions. | Source-layer retry/backoff, alerts, and stop conditions. |
| Payload / format | Broken CSV, invalid JSON schema, missing required fields. | Validation and quarantine; do not retry bad data infinitely. |
| Internal delivery | Channel has no consumer, queue full, or endpoint stopped. | Monitor queue/channel depth, bound load, and recover endpoints. |
| Target rejection or timeout | HTTP 429/5xx, broker unavailable. | Bounded retries, backoff, idempotency, and DLQ/quarantine. |
| Uncertain outcome | Target persisted write but response lost. | Reconcile by business ID; avoid repeating side effects. |

With synchronous channels like `DirectChannel`, handler exceptions can surface directly on the send call. With queues, executors, or brokers, errors may occur on different threads and require an error channel or adapter error handlers. A poller firing again does not replace proper layered retry design.

### 11.3. Lifecycle and Multiple Instances

When the Spring context starts, endpoints can auto-start according to lifecycle settings. On shutdown, address: stopping new polls, draining in-flight messages, releasing SFTP/JMS/DB sessions, closing thread pools, and saving checkpoints safely.

If two instances poll the same directory or database table, both can see the same item. A per-instance in-memory filter cannot prevent cross-process duplicates. Use locking, partitioning, record claiming, or a persistent metadata store suited to the source.

Useful metrics: messages received, files processed, poll duration, handler latency, errors per adapter, queue depth, retries, dead-letter counts, and reconnect counts.

## 12. Targeted Testing of XML Configuration

Distinguish three layers of testing:

- **Context wiring:** XML parses cleanly, beans/channels/endpoints exist, Java methods resolve.
- **Message flow:** sending messages to channels triggers transformers/handlers with expected payload types and headers.
- **External behavior:** real files emitted/written, SFTP reconnects, HTTP timeouts, JMS acks, DB transactions, and restart deduplication.

### 12.1. Testing XML Wiring Without Waiting for the Poller

With `CsvFileProcessor` from section 4, test that the channel invokes the service activator inside the same Spring context. Create `src/test/java/demo/xmladapter/XmlAdapterWiringTest.java`:

~~~java
package demo.xmladapter;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest
class XmlAdapterWiringTest {

    @Autowired
    @Qualifier("files.input")
    MessageChannel input;

    @Autowired
    CsvFileProcessor processor;

    @Test
    void xmlServiceActivatorReceivesFilePayload() throws Exception {
        Path csv = Files.createTempFile("xml-adapter-", ".csv");
        try {
            Files.writeString(csv,
                    "orderId,amount\nORD-1001,250000\n",
                    StandardCharsets.UTF_8);

            boolean sent = input.send(
                    MessageBuilder.withPayload(csv.toFile()).build());

            assertTrue(sent);
            assertTrue(processor.wasHandled(csv));
        } finally {
            Files.deleteIfExists(csv);
        }
    }
}
~~~

Test dependency declaration:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

This test proves **XML channel → service activator → Java bean** is wired and runs synchronously. It **does not prove the poller detected a file**, because the test sends the message directly. In test environments, ensure `./inbox` exists or configure a test-specific directory so the inbound endpoint starts cleanly.

### 12.2. Testing Real Inbound Polling

To test the file inbound adapter:

1. Use an isolated temporary directory for the test and bind `adapter.inbox` to it **before the context is created**.
2. Write one `.csv` file and one `.txt` file with distinct names and contents.
3. Use a latch or timed wait condition to verify the processor receives the CSV file. Do not assert exact file ordering unless the adapter guarantees order.
4. Confirm the `.txt` file does not reach the handler, and test partially written files.
5. Restart the context to test duplicate behavior, since in-memory filter state is lost.

For outbound adapters, verify the file is actually created in the expected location with matching name and content; then test existing target files, permission denials, and mid-write failures.

## 13. Common Configuration Errors

| Symptom | Likely Cause | How to Check |
| --- | --- | --- |
| Startup fails to recognize `int-file:...` tags. | Missing namespace, wrong schema, or missing `spring-integration-file`. | Inspect `xmlns`, `xsi:schemaLocation`, and dependencies. |
| Spring fails to resolve `${adapter.inbox}`. | Properties not loaded or wrong key name. | Check `<context:property-placeholder>`, classpath, and profiles. |
| Poller runs with no messages emitted. | Empty folder, wrong path, wrong pattern, or filtered out. | Verify working directory, source contents, and filter rules. |
| Messages enter channel but are never processed. | Mismatched `input-channel` or missing consumer. | Compare channel IDs and verify endpoint startup state. |
| Flow processes slowly despite fast poller. | `DirectChannel` and blocking handler. | Measure handler duration, timeouts, and poll limits. |
| Same file processed twice after restart. | Non-persistent deduplication state. | Use persistent state, archiving, and idempotency. |
| Outbound fails with file-already-exists error. | Unsuitable naming rule or file-exists mode. | Choose unique naming/replace/fail strategy and test it. |
| Two consumers exist, yet only one runs. | `DirectChannel` does not broadcast by default. | Use `PublishSubscribeChannel` when fan-out is truly needed. |
| Gateway waiting for reply never receives one. | One-way adapter or filter drops message. | Separate request–reply from one-way and design reply paths. |
| XML breaks after framework upgrade. | Deprecated attributes or schema parser changes. | Check the XSD for the exact Spring Integration version. |

## 14. Extended Practice Exercise

**Scenario:** a system receives payment files from a directory and sends records to a partner service. Build an XML configuration meeting these requirements:

1. Create `<int-file:inbound-channel-adapter>` scanning `./inbox` every 3 seconds, accepting only `payment-*.csv`, capped at 4 messages per poll.
2. Declare channel `payments.files` and a Java service activator that parses CSV files, converting each row into a valid `PaymentCommand`.
3. Separate the file-intake flow from the per-command processing flow, carrying `sourceFile`, `correlationId`, and `idempotencyKey` metadata.
4. Route messages to an outbound endpoint (file or simulated client/service) and record completion status by ID.
5. Files failing schema validation must move to a review quarantine with error details for correction and replay.
6. Simulate a destination timeout after receiving a command; prove retries do not create duplicate records.
7. Swap the local file source for SFTP, adding a session factory bean, remote file filters, local sync rules, and a reconnect policy.
8. Run two instances polling the same source and explain what mechanism prevents duplicate processing.

**Pass criteria:** XML boots cleanly in the Spring context; channel names match; the poller enforces the message cap; message contracts specify payload/headers; tests cover errors, retries, restarts, and duplicates. For the same design written in Java DSL, map out the corresponding beans and endpoints between both styles.

## 15. Self-Check Questions

1. How do `xmlns:int` and `xmlns:int-file` differ in responsibility?
2. Why are both the namespace/XSD declaration and the module dependency required?
3. How does `id="csvInbound"` differ from `channel="files.input"`?
4. Why does a file inbound adapter need `<int:poller>` while an HTTP inbound gateway normally does not?
5. Does `max-messages-per-poll="5"` count messages or lines inside a file?
6. In `<int:service-activator>`, what do `ref` and `method` point to?
7. If XML declares two consumers on the same `DirectChannel`, do both receive the same message?
8. Why does a successful `MessageChannel.send()` not prove the partner completed the transaction?
9. What happens when deduplication state is kept only in memory and the application restarts?
10. Can XML and Java DSL coexist in the same application? Which conflicts must be avoided?

**Answer hints:** namespaces map XML tags to Spring Integration parsers and beans; channel IDs connect endpoints; pollers drive sources that actively pull messages; service activators invoke Java logic; durability and business confirmation belong to source/destination contracts and integration state.

## 16. Key Takeaways

Configuring adapters with **XML namespaces** lets you declare inbound sources, channels, pollers, processing steps, and external destinations explicitly. For example, `int-file:inbound-channel-adapter` paired with `int:poller`, `int:channel`, and `int:service-activator` forms a complete flow from files to a Java handler without writing all wiring in the Java DSL.

When switching to SFTP, HTTP, JMS, AMQP, Kafka, or databases, the **message contract** and channel/adapter/gateway concepts carry over; namespaces, connection/session factories, acknowledgements, timeouts, and retries must be configured per protocol. System quality depends on verifying that flows register properly, data recovers from failures, and outbound side effects are never executed twice.
